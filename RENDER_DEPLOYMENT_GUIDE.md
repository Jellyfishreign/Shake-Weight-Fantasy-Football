# 🚀 Render.com Deployment Guide

## Quick Start - Deploy to Render in 10 Minutes

### Prerequisites
- ✅ Code pushed to GitHub (your repo: Shake-Weight-Fantasy-Football)
- ✅ Google Sheets credentials JSON file on your computer
- ✅ Render.com account (free)

---

## Step-by-Step Deployment

### 1️⃣ Sign Up for Render

1. Go to [https://render.com](https://render.com)
2. Click **"Get Started"**
3. Choose **"Sign up with GitHub"**
4. Authorize Render to access your repositories

---

### 2️⃣ Create New Web Service

1. In Render dashboard, click **"New +"** button (top right)
2. Select **"Web Service"**
3. Find and select: **"Shake-Weight-Fantasy-Football"**
4. Click **"Connect"**

---

### 3️⃣ Configure Your Service

Fill in these settings:

| Setting | Value |
|---------|-------|
| **Name** | `shake-weight-fantasy` (or whatever you prefer) |
| **Region** | Choose closest to you (e.g., Oregon USA) |
| **Branch** | `main` |
| **Root Directory** | Leave blank |
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python app.py` |
| **Instance Type** | **Free** |

---

### 4️⃣ Add Environment Variables

**CRITICAL STEP:** You need to add your Google Sheets credentials

#### 4a. Get Your Credentials JSON

1. On your computer, open this file:
   ```
   C:\Users\Seth\Documents\Phython\PyCharm Projects\PythonProject\automating_APIs\Sleeper API\sleeper_gsheet_creds.json
   ```

2. **Copy the ENTIRE file contents**
   
3. **Remove all line breaks** to make it ONE SINGLE LINE
   - Example: `{"type":"service_account","project_id":"your-id","private_key_id":"abc123",...}`

#### 4b. Add to Render

1. In the configuration page, scroll to **"Environment Variables"**
2. Click **"Add Environment Variable"**
3. Enter:
   - **Key:** `GOOGLE_SHEETS_CREDS_JSON`
   - **Value:** Paste the one-line JSON you copied
4. Click **"Add"**

#### 4c. Optional: Add Debug Mode

1. Add another environment variable:
   - **Key:** `DEBUG`
   - **Value:** `False`

---

### 5️⃣ Deploy!

1. Click **"Create Web Service"** (bottom of page)
2. Wait 2-5 minutes for deployment
3. Watch the logs scroll by
4. Look for: `[OK] Data update complete`
5. Status will change to **"Live"** with a green dot

---

### 6️⃣ Get Your App URL

After deployment succeeds:

1. Your app will be at: `https://shake-weight-fantasy.onrender.com`
   (or whatever name you chose)
2. Click the URL to test it
3. You should see your dashboard with live data!

---

## 🔄 Update GitHub Pages to Use Live Backend

Now that your backend is deployed, update your GitHub Pages site:

### Option A: Simple Redirect (Recommended)

Replace your current `index.html` on GitHub Pages with a redirect:

1. Go to your GitHub repo
2. Click on `index.html`
3. Click the pencil icon to edit
4. Replace ALL content with the contents of `index_github_pages.html` (I created this for you)
5. **IMPORTANT:** In the file, replace:
   ```javascript
   const BACKEND_URL = 'https://YOUR-APP-NAME.onrender.com';
   ```
   With your actual Render URL:
   ```javascript
   const BACKEND_URL = 'https://shake-weight-fantasy.onrender.com';
   ```
6. Commit the changes

### Option B: Direct Backend Access (Alternative)

Just tell people to use your Render URL directly:
- `https://shake-weight-fantasy.onrender.com`

You can keep GitHub Pages as a backup/redirect.

---

## 🎯 Testing Your Deployment

### Test Checklist:

1. ✅ Visit `https://shake-weight-fantasy.onrender.com`
2. ✅ Dashboard loads with live data
3. ✅ Payouts tab shows correct data
4. ✅ Quantum Gauntlet shows tournament data
5. ✅ GitHub Pages redirects properly (if using redirect)

### Common Issues:

**Problem:** "Application failed to respond"
- **Solution:** Check Render logs, make sure environment variable is set correctly

**Problem:** "502 Bad Gateway"  
- **Solution:** App is starting (wait 60 seconds for free tier to wake up)

**Problem:** No data showing
- **Solution:** Check Google Sheets credentials in environment variables

---

## 📊 Monitoring & Logs

### View Logs:
1. Go to Render dashboard
2. Click your service name
3. Click **"Logs"** tab
4. See real-time application logs

### Manual Restart:
1. In Render dashboard
2. Click **"Manual Deploy"** → **"Clear build cache & deploy"**

---

## 💰 Cost

**Current Setup:** **$0/month**
- Render Free tier includes:
  - 750 hours/month (your app will use ~720)
  - Automatic SSL (HTTPS)
  - Auto-restarts if crashes
  - Note: Sleeps after 15 mins of inactivity

---

## 🔄 Updating Your App

Whenever you make code changes:

```bash
cd "C:\Users\Seth\Documents\SWF 26 Playoff Code"
git add .
git commit -m "Description of changes"
git push origin main
```

Render will **automatically re-deploy** within 2-3 minutes!

---

## Need Help?

If you encounter issues:
1. Check Render logs first
2. Verify environment variables are set
3. Make sure Google Sheets credentials are valid
4. Check that your GitHub repo is up to date

