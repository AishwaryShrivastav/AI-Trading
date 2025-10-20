# Fixing Upstox OAuth Error UDAPI100068

## Error Details
```
errorCode: "UDAPI100068"
message: "Check your 'client_id' and 'redirect_uri'; one or both are incorrect."
```

## Root Cause
The redirect URI in your Upstox Developer Dashboard doesn't match the one configured in the application.

---

## ✅ SOLUTION (5 Minutes)

### Step 1: Go to Upstox Developer Portal
```
https://account.upstox.com/developer/apps
```

### Step 2: Update Your App Settings

**Your app must have these EXACT settings:**

```
Client ID: 02c3528d-9f83-45d2-9da4-202bb3a9804e

Redirect URI: http://localhost:8000/api/auth/upstox/callback
              ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
              COPY THIS EXACTLY - NO CHANGES!
```

**Critical Points:**
- ✅ Use `http://` NOT `https://`
- ✅ Include port `:8000`
- ✅ Full path: `/api/auth/upstox/callback`
- ❌ NO trailing slash
- ❌ NO extra spaces before or after

### Step 3: Save and Wait

1. Click "Save" or "Update" in Upstox dashboard
2. Wait 1-2 minutes for changes to sync

### Step 4: Restart the Server

```bash
cd /Users/aishwary/Development/AI-Investment
source venv/bin/activate

# Stop current server
pkill -f uvicorn

# Start fresh
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 5: Test Login

1. Open http://localhost:8000
2. Click "Login with Upstox"
3. Should redirect to Upstox login page ✅
4. Enter credentials
5. Grant permissions
6. Redirects back to your app ✅
7. Shows "✓ Authenticated" ✅

---

## 🔍 VERIFICATION CHECKLIST

Before trying again, verify:

- [ ] Upstox dashboard redirect URI: `http://localhost:8000/api/auth/upstox/callback`
- [ ] Client ID matches in both places
- [ ] No https:// (use http:// for localhost)
- [ ] Port :8000 is included
- [ ] Full path /api/auth/upstox/callback is included
- [ ] No trailing slash at the end
- [ ] Saved changes in Upstox dashboard
- [ ] Waited 1-2 minutes
- [ ] Restarted the server

---

## 📸 Screenshot Guidance

**In Upstox Developer Dashboard, it should look like:**

```
┌─────────────────────────────────────────────────────────┐
│ App Details                                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ App Name:         AI Trading System                     │
│                                                         │
│ Client ID:        02c3528d-9f83-45d2-9da4-202bb3a9804e │
│                                                         │
│ Client Secret:    u7pbu53l1l...                        │
│                                                         │
│ Redirect URI:     http://localhost:8000/api/auth/upstox/callback │
│                   ↑ THIS MUST MATCH EXACTLY ↑           │
│                                                         │
│ [Save]                                                  │
└─────────────────────────────────────────────────────────┘
```

---

## 🆘 Alternative Solutions

### Option A: Use Different Port

If port 8000 is causing issues, you can use port 3000:

1. **In Upstox Dashboard:**
   ```
   Redirect URI: http://localhost:3000/api/auth/upstox/callback
   ```

2. **In .env file:**
   ```
   UPSTOX_REDIRECT_URI=http://localhost:3000/api/auth/upstox/callback
   API_PORT=3000
   ```

3. **Restart server on port 3000:**
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 3000 --reload
   ```

### Option B: Use 127.0.0.1 Instead of localhost

Some systems prefer IP address:

1. **In Upstox Dashboard:**
   ```
   Redirect URI: http://127.0.0.1:8000/api/auth/upstox/callback
   ```

2. **In .env file:**
   ```
   UPSTOX_REDIRECT_URI=http://127.0.0.1:8000/api/auth/upstox/callback
   ```

### Option C: Production Domain (If Deployed)

If you've deployed to a domain:

1. **In Upstox Dashboard:**
   ```
   Redirect URI: https://your-domain.com/api/auth/upstox/callback
   ```

2. **In .env file:**
   ```
   UPSTOX_REDIRECT_URI=https://your-domain.com/api/auth/upstox/callback
   ```

---

## 📞 Still Not Working?

### Double-Check These:

1. **Client ID Format:**
   - Should be a UUID format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - Must match exactly between Upstox and .env

2. **Redirect URI Format:**
   - Must start with `http://` or `https://`
   - Must include domain/IP
   - Must include port (if not 80/443)
   - Must include full path
   - No query parameters

3. **App Status in Upstox:**
   - Make sure app is "Active" or "Approved"
   - Not in "Pending" or "Suspended" state

4. **API Version:**
   - We're using Upstox API v2
   - Make sure your app supports v2

---

## 🎯 MOST COMMON FIX

**99% of the time, the issue is:**

The redirect URI in Upstox dashboard has:
- Extra trailing slash: `http://localhost:8000/api/auth/upstox/callback/` ❌
- Missing http://: `localhost:8000/api/auth/upstox/callback` ❌
- Wrong port: `http://localhost:3000/api/auth/upstox/callback` ❌

**Should be:**
```
http://localhost:8000/api/auth/upstox/callback
```

**Copy this EXACTLY into Upstox dashboard!**

---

## ✅ Once Fixed

You'll be able to:
1. Login with Upstox ✅
2. Approve trades ✅
3. Place orders automatically ✅
4. Track positions ✅
5. View account funds ✅

Let me know once you've updated the Upstox dashboard, and I'll help you test!


