#!/usr/bin/env python3
"""
Auth Flow Testing - Rate Limit Lockout Verification
Tests admin login flow after clearing rate-limit lockout
"""
import requests
import json
import sys

# Configuration
BASE_URL = "https://repo-link-17.preview.emergentagent.com/api"
ADMIN_EMAIL = "msabhadiya007@gmail.com"
ADMIN_PASSWORD = "Admin@12345"

class AuthTestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.token = None
        
    def log(self, message: str, level: str = "INFO"):
        """Log test messages"""
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "ℹ️"
        print(f"{prefix} {message}")
        
    def test_result(self, condition: bool, message: str, details: any = None):
        """Record test result"""
        if condition:
            self.log(f"PASS: {message}", "PASS")
            self.passed += 1
        else:
            self.log(f"FAIL: {message}", "FAIL")
            if details:
                print(f"   Details: {json.dumps(details, indent=2) if isinstance(details, dict) else details}")
            self.failed += 1
        return condition
        
    def test_1_successful_login(self):
        """Test 1: Successful login with correct credentials"""
        self.log("\n=== TEST 1: SUCCESSFUL LOGIN ===")
        self.log(f"POST {BASE_URL}/auth/login with correct credentials")
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            
            # Check status code is 200 (not 429)
            if not self.test_result(
                response.status_code == 200,
                "Login returns HTTP 200 (not 429 - lockout cleared)",
                {"status_code": response.status_code, "body": response.text[:200]}
            ):
                return False
                
            # Check response body
            try:
                data = response.json()
            except Exception:
                self.test_result(False, "Response is valid JSON", response.text[:200])
                return False
                
            # Check token field exists and is non-empty
            self.token = data.get("token")
            if not self.test_result(
                self.token and len(self.token) > 0,
                "Response contains non-empty 'token' field",
                {"token_present": bool(self.token), "token_length": len(self.token) if self.token else 0}
            ):
                return False
                
            # Check user object exists
            user = data.get("user")
            if not self.test_result(
                user is not None,
                "Response contains 'user' object",
                {"user_present": bool(user)}
            ):
                return False
                
            # Check user role is admin
            self.test_result(
                user.get("role") == "admin",
                "User role is 'admin'",
                {"role": user.get("role")}
            )
            
            self.log(f"✓ Login successful, token: {self.token[:30]}...")
            return True
            
        except Exception as e:
            self.test_result(False, f"Login request failed with exception: {e}")
            return False
            
    def test_2_token_works(self):
        """Test 2: Token works for /api/auth/me"""
        self.log("\n=== TEST 2: TOKEN WORKS ===")
        self.log(f"GET {BASE_URL}/auth/me with Bearer token")
        
        if not self.token:
            self.test_result(False, "Cannot test /auth/me - no token from previous test")
            return False
            
        try:
            response = requests.get(
                f"{BASE_URL}/auth/me",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            
            # Check status code is 200
            if not self.test_result(
                response.status_code == 200,
                "GET /auth/me returns HTTP 200",
                {"status_code": response.status_code, "body": response.text[:200]}
            ):
                return False
                
            # Check response body
            try:
                data = response.json()
            except Exception:
                self.test_result(False, "Response is valid JSON", response.text[:200])
                return False
                
            # Check user object
            user = data.get("user")
            if not self.test_result(
                user is not None,
                "Response contains 'user' object",
                {"user_present": bool(user)}
            ):
                return False
                
            # Check user is admin
            self.test_result(
                user.get("role") == "admin",
                "User role is 'admin'",
                {"role": user.get("role"), "email": user.get("email")}
            )
            
            # Check permissions list exists
            permissions = data.get("permissions")
            self.test_result(
                permissions is not None and isinstance(permissions, list),
                "Response contains 'permissions' list",
                {"permissions": permissions}
            )
            
            self.log(f"✓ Token authentication successful")
            return True
            
        except Exception as e:
            self.test_result(False, f"/auth/me request failed with exception: {e}")
            return False
            
    def test_3_wrong_password_rejected(self):
        """Test 3: Wrong password is rejected with 401 (not 429)"""
        self.log("\n=== TEST 3: WRONG PASSWORD STILL REJECTED ===")
        self.log(f"POST {BASE_URL}/auth/login with wrong password")
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": "wrongpass"},
                timeout=10
            )
            
            # Check status code is 401 (not 429)
            if not self.test_result(
                response.status_code == 401,
                "Wrong password returns HTTP 401 (not 429)",
                {"status_code": response.status_code, "body": response.text[:200]}
            ):
                return False
                
            # Check error message
            try:
                data = response.json()
                detail = data.get("detail", "")
            except Exception:
                detail = response.text
                
            self.test_result(
                "Invalid email or password" in detail,
                "Error message is 'Invalid email or password'",
                {"detail": detail}
            )
            
            self.log(f"✓ Wrong password correctly rejected with 401")
            return True
            
        except Exception as e:
            self.test_result(False, f"Wrong password test failed with exception: {e}")
            return False
            
    def test_4_correct_login_after_wrong(self):
        """Test 4: Correct login still works after a wrong attempt"""
        self.log("\n=== TEST 4: CORRECT LOGIN AFTER WRONG ATTEMPT ===")
        self.log(f"POST {BASE_URL}/auth/login with correct credentials again")
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            
            # Check status code is 200 (not 429)
            if not self.test_result(
                response.status_code == 200,
                "Login returns HTTP 200 (account not re-locked)",
                {"status_code": response.status_code, "body": response.text[:200]}
            ):
                return False
                
            # Check response body
            try:
                data = response.json()
            except Exception:
                self.test_result(False, "Response is valid JSON", response.text[:200])
                return False
                
            # Check token field exists
            token = data.get("token")
            self.test_result(
                token and len(token) > 0,
                "Response contains valid token",
                {"token_present": bool(token)}
            )
            
            self.log(f"✓ Login successful after wrong attempt - no re-lock")
            return True
            
        except Exception as e:
            self.test_result(False, f"Login after wrong attempt failed with exception: {e}")
            return False
            
    def run_all_tests(self):
        """Run all auth tests"""
        self.log("=" * 70)
        self.log("AUTH FLOW TESTING - Rate Limit Lockout Verification")
        self.log("=" * 70)
        
        # Run tests in sequence
        self.test_1_successful_login()
        self.test_2_token_works()
        self.test_3_wrong_password_rejected()
        self.test_4_correct_login_after_wrong()
        
        # Summary
        self.log("\n" + "=" * 70)
        self.log(f"SUMMARY: {self.passed} passed, {self.failed} failed")
        self.log("=" * 70)
        
        if self.failed > 0:
            self.log("\n⚠️  Some tests failed. Login flow has issues.", "FAIL")
            return False
        else:
            self.log("\n✅ All auth tests passed. Login flow is working correctly.", "PASS")
            return True

if __name__ == "__main__":
    runner = AuthTestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)
