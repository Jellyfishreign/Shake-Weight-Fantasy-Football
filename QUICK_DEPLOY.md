# 🚀 Quick Deploy Commands

## After Installing Git, Run These Commands:

### 1. Navigate to your project
```powershell
cd "C:\Users\Seth\Documents\SWF 26 Playoff Code"
```

### 2. Configure Git (FIRST TIME ONLY)
```powershell
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 3. Add all files to Git
```powershell
git add .
```

### 4. Commit your changes
```powershell
git commit -m "Prepare for Render deployment"
```

### 5. Push to GitHub
```powershell
git push origin main
```

---

## Then Deploy on Render.com:

1. **Go to:** [https://render.com](https://render.com)
2. **Sign up** with GitHub
3. **New + → Web Service**
4. **Select** your "Shake-Weight-Fantasy-Football" repo
5. **Configure:**
   - Name: `shake-weight-fantasy`
   - Build: `pip install -r requirements.txt`
   - Start: `python app.py`
   - Free tier
6. **Add Environment Variable:**
   - Key: `GOOGLE_SHEETS_CREDS_JSON`
   - Value: (Copy entire content from your credentials file as ONE LINE)
7. **Click "Create Web Service"**
8. **Wait 3-5 minutes**
9. **Done!** Your URL: `https://shake-weight-fantasy.onrender.com`

---

## Update GitHub Pages (Optional)

If you want to keep `jellyfishreign.github.io/Shake-Weight-Fantasy-Football/`:

1. Open: `index_github_pages.html` (I created this file)
2. Replace `YOUR-APP-NAME` with your actual Render app name
3. Upload this as your new `index.html` on GitHub Pages
4. It will auto-redirect visitors to your live site!

---

## 🎉 That's It!

Your app will be live at your Render URL with:
- ✅ Real-time data from Sleeper API
- ✅ Automatic updates every hour
- ✅ Live WebSocket connections
- ✅ All your latest changes
- ✅ Free hosting!

