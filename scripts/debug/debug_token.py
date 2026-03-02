#!/usr/bin/env python3
"""
Debug script to decode JWT token and check permissions extraction.
"""
import jwt
import sys
from datetime import datetime

def decode_token(token):
    """Decode JWT token without verification to inspect claims."""
    try:
        # Decode without verification to see what's in the token
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        print("=" * 80)
        print("TOKEN CLAIMS:")
        print("=" * 80)
        for key, value in decoded.items():
            if key == "exp":
                exp_time = datetime.fromtimestamp(value)
                print(f"{key}: {value} ({exp_time})")
            else:
                print(f"{key}: {value}")
        
        print("\n" + "=" * 80)
        print("PERMISSION EXTRACTION SIMULATION:")
        print("=" * 80)
        
        # Simulate the permission extraction logic from get_current_user
        permissions_set = set()
        
        # 1. Check explicit permissions claim (Auth0 style)
        perm_claim = decoded.get("permissions")
        print(f"\n1. permissions claim: {perm_claim}")
        if isinstance(perm_claim, (list, tuple)):
            permissions_set.update(str(p) for p in perm_claim if p)
            print(f"   Added to set: {[str(p) for p in perm_claim if p]}")
        
        # 2. Check scope claim (space-separated string)
        scope_claim = decoded.get("scope")
        print(f"\n2. scope claim: {scope_claim}")
        if isinstance(scope_claim, str):
            scopes_from_claim = [s for s in scope_claim.split() if s]
            permissions_set.update(scopes_from_claim)
            print(f"   Added to set: {scopes_from_claim}")
        
        # 3. Check scopes claim (array)
        scopes_claim = decoded.get("scopes")
        print(f"\n3. scopes claim: {scopes_claim}")
        if isinstance(scopes_claim, (list, tuple)):
            scopes_from_claim = [str(s) for s in scopes_claim if s]
            permissions_set.update(scopes_from_claim)
            print(f"   Added to set: {scopes_from_claim}")
        
        # 4. Check roles claim - admin role grants admin:all
        roles_claim = decoded.get("roles")
        print(f"\n4. roles claim: {roles_claim}")
        if isinstance(roles_claim, (list, tuple)):
            roles_list = [str(r) for r in roles_claim if r]
            print(f"   Roles found: {roles_list}")
            if any(r.lower() == "admin" for r in roles_list):
                permissions_set.add("admin:all")
                print(f"   Added 'admin:all' due to admin role")
        
        print("\n" + "=" * 80)
        print("FINAL PERMISSIONS SET:")
        print("=" * 80)
        permissions_list = sorted(list(permissions_set))
        print(f"Permissions: {permissions_list}")
        
        print("\n" + "=" * 80)
        print("PERMISSION CHECK:")
        print("=" * 80)
        print(f"Has 'user:me': {'user:me' in permissions_list}")
        print(f"Has 'admin:all': {'admin:all' in permissions_list}")
        print(f"Has 'user:me' OR 'admin:all': {'user:me' in permissions_list or 'admin:all' in permissions_list}")
        
        if 'user:me' in permissions_list or 'admin:all' in permissions_list:
            print(f"\n✅ TOKEN SHOULD BE ACCEPTED by /v1/models/defaults")
        else:
            print(f"\n❌ TOKEN WILL BE REJECTED by /v1/models/defaults")
            print(f"   Missing required scopes: user:me OR admin:all")
        
        return True
    
    except Exception as e:
        print(f"Error decoding token: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_token.py <JWT_TOKEN>")
        print("\nYou can get your token from the UI's Auth tab or from environment variables.")
        sys.exit(1)
    
    token = sys.argv[1]
    decode_token(token)
