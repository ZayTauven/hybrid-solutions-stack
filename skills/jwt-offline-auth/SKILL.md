# Skill: JWT Offline Authentication

**Purpose:** Implement JWT-based auth that works offline for up to 24h.

**Outputs:**
- ✅ JWT token generation (access + refresh)
- ✅ Local token validation (no server needed)
- ✅ Offline session persistence
- ✅ Token refresh strategy
- ✅ Logout handling

---

## Architecture

```
Login Flow:
User Email/Password
    ↓ POST /api/auth/login
    ↓
Django validates
    ↓
Returns JWT tokens
    ↓
Store in SecureStore (mobile) / LocalStorage encrypted (web)
    ↓
Decode & verify locally
    ↓
Allow app access
```

---

## Django Backend

```python
# views.py
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.response import Response

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims
        token['tenant_id'] = str(user.profile.current_tenant_id)
        token['email'] = user.email
        token['name'] = user.get_full_name()
        token['roles'] = list(user.groups.values_list('name', flat=True))
        
        return token

class TokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

# settings.py
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': settings.SECRET_KEY,
}
```

---

## Frontend: Offline Validation

```typescript
// lib/auth/useAuth.ts
import jwt_decode from 'jwt-decode';
import SecureStore from 'expo-secure-store';  // Mobile
// Or crypto-js for web

interface DecodedToken {
  sub: string;
  tenant_id: string;
  email: string;
  exp: number;
  iat: number;
}

export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<DecodedToken | null>(null);
  
  useEffect(() => {
    // On app start: validate stored token
    validateStoredToken();
  }, []);
  
  async function validateStoredToken() {
    try {
      const token = await SecureStore.getItemAsync('access_token');
      if (!token) {
        setIsAuthenticated(false);
        return;
      }
      
      // Decode (NO verification needed offline)
      const decoded = jwt_decode<DecodedToken>(token);
      
      // Check expiry
      if (decoded.exp * 1000 < Date.now()) {
        // Try refresh
        await refreshToken();
        return;
      }
      
      setUser(decoded);
      setIsAuthenticated(true);
    } catch (error) {
      console.error('Token validation failed:', error);
      setIsAuthenticated(false);
    }
  }
  
  async function login(email: string, password: string) {
    const res = await fetch('/api/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    if (!res.ok) throw new Error('Login failed');
    
    const { access, refresh } = await res.json();
    
    // Store tokens securely
    await SecureStore.setItemAsync('access_token', access);
    await SecureStore.setItemAsync('refresh_token', refresh);
    
    // Update state
    const decoded = jwt_decode<DecodedToken>(access);
    setUser(decoded);
    setIsAuthenticated(true);
  }
  
  async function refreshToken() {
    try {
      const refresh = await SecureStore.getItemAsync('refresh_token');
      if (!refresh) throw new Error('No refresh token');
      
      const res = await fetch('/api/auth/refresh/', {
        method: 'POST',
        body: JSON.stringify({ refresh }),
      });
      
      if (!res.ok) {
        // Refresh failed, logout
        logout();
        return;
      }
      
      const { access } = await res.json();
      await SecureStore.setItemAsync('access_token', access);
      
      const decoded = jwt_decode<DecodedToken>(access);
      setUser(decoded);
    } catch (error) {
      logout();
    }
  }
  
  function logout() {
    SecureStore.deleteItemAsync('access_token');
    SecureStore.deleteItemAsync('refresh_token');
    setIsAuthenticated(false);
    setUser(null);
  }
  
  return { isAuthenticated, user, login, logout, refreshToken };
}
```

---

## API Requests with Token

```typescript
// lib/api/client.ts
import SecureStore from 'expo-secure-store';
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: 'https://api.example.com',
});

// Add token to every request
apiClient.interceptors.request.use(async (config) => {
  const token = await SecureStore.getItemAsync('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 (token expired)
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      try {
        const refresh = await SecureStore.getItemAsync('refresh_token');
        const res = await axios.post('/api/auth/refresh/', { refresh });
        
        await SecureStore.setItemAsync('access_token', res.data.access);
        
        // Retry original request
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Logout
        await SecureStore.deleteItemAsync('access_token');
        await SecureStore.deleteItemAsync('refresh_token');
        
        // Redirect to login
        window.location.href = '/login';
        throw refreshError;
      }
    }
    
    return Promise.reject(error);
  }
);
```

---

## Logout & Cleanup

```typescript
async function logout() {
  try {
    // Notify server (best effort)
    await apiClient.post('/api/auth/logout/');
  } catch (error) {
    // Offline, continue anyway
  }
  
  // Clear local storage
  await SecureStore.deleteItemAsync('access_token');
  await SecureStore.deleteItemAsync('refresh_token');
  
  // Clear app state
  useAuthStore.reset();
  
  // Redirect
  router.push('/login');
}
```

---

## Token Payload Example

```json
{
  "sub": "user_uuid_123",
  "email": "user@example.com",
  "name": "Jean Dupont",
  "tenant_id": "tenant_cmr_001",
  "roles": ["admin", "invoice_approver"],
  "permissions": ["invoice:create", "invoice:approve"],
  "iat": 1695148800,
  "exp": 1695235200,
  "iss": "hybrid-erp"
}
```

---

## Token Rotation (Optional)

```python
# views.py
class TokenRotationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Rotate tokens (call weekly for extra security)"""
        user = request.user
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
```

