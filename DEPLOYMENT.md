# Deployment Guide for Shake Weight Fantasy Dashboard

## Environment Variables Required

When deploying to Render.com or other hosting services, you need to set these environment variables:

### Required Variables:

1. **GOOGLE_SHEETS_CREDS_JSON**
   - Your Google Sheets service account credentials as a JSON string
   - Get this from: `C:\Users\Seth\Documents\Phython\PyCharm Projects\PythonProject\automating_APIs\Sleeper API\sleeper_gsheet_creds.json`
   - Copy the ENTIRE contents of that file and paste as ONE LINE (no line breaks)
   - Example format: `{"type":"service_account","project_id":"your-project-id",...}`

### Optional Variables:

2. **PORT**
   - Automatically set by hosting service
   - Default: 5004 (for local development)

3. **DEBUG**
   - Set to `False` for production
   - Default: False

---

## Deploy to Render.com (Recommended)

### Step 1: Push Code to GitHub

```bash
cd "C:\Users\Seth\Documents\SWF 26 Playoff Code"
git add .
git commit -m "Prepare for deployment"
git push origin main
```

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Authorize Render to access your repositories

### Step 3: Create New Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your **"Shake-Weight-Fantasy-Football"** repository
3. Configure:
   - **Name:** `shake-weight-fantasy`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
   - **Instance Type:** Free

### Step 4: Add Environment Variables

1. In Render dashboard, go to **"Environment"** tab
2. Click **"Add Environment Variable"**
3. Add: `GOOGLE_SHEETS_CREDS_JSON`
4. Value: Paste your entire Google Sheets credentials JSON (as one line)
5. Click **"Save Changes"**

### Step 5: Deploy

1. Click **"Manual Deploy"** → **"Deploy latest commit"**
2. Wait 2-3 minutes for deployment
3. Your app will be live at: `https://shake-weight-fantasy.onrender.com`

---

## Connect GitHub Pages to Live Backend

After deploying to Render, update your GitHub Pages site to use the live data:

### Update Socket.IO Connection

In your `index.html` on GitHub, find:

```javascript
const socket = io();
```

Change to:

```javascript
const socket = io('https://your-app-name.onrender.com');
```

### Update API Calls

Find:

```javascript
fetch('/api/data')
```

Change to:

```javascript
fetch('https://your-app-name.onrender.com/api/data')
```

---

## Enable CORS for GitHub Pages

You'll need to allow GitHub Pages to connect to your Render backend. This is already configured in `app.py` with:

```python
socketio = SocketIO(app, cors_allowed_origins="*")
```

---

## Important Notes

- **Free Tier Sleep:** Render free tier sleeps after 15 mins of inactivity
- **First Load:** May take 30-60 seconds to wake up
- **Auto Updates:** Background thread updates data every hour
- **Cost:** Completely free for this usage level

---

## Testing Deployment

After deployment:

1. Visit `https://your-app-name.onrender.com` directly (should show your dashboard)
2. Check logs in Render dashboard for any errors
3. Update GitHub Pages to connect to this URL
4. Test that GitHub Pages loads live data

