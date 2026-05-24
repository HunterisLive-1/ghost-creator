# YouTube Analytics API — Step-by-Step Setup Guide

Google Account connect karne ke liye aapko Google Cloud Console se ek **Desktop Application OAuth Credentials** JSON file download karke apne project folder me save karni hogi. 

Neeche diye gaye steps ko follow karke aap ise 5 minute me setup kar sakte hain.

---

## Step 1 — Google Cloud Console par Project banayein
1. **[console.cloud.google.com](https://console.cloud.google.com)** kholiye (apne kisi bhi Google account se login karein).
2. Top left me **"Select a project"** dropdown par click karein aur **"New Project"** par click karein.
3. Project Name me `Ghost Creator AI` dalein aur **"Create"** par click karein.
4. Project create hone ke baad, top right notifications se ya usi dropdown se use **Select** kar lein.

---

## Step 2 — YouTube APIs ko Enable karein
1. Left sidebar menu kholiye aur **"APIs & Services"** → **"Library"** par click karein.
2. Search box me `YouTube Data API v3` search karein aur use **Enable** karein.
3. Fir se Library me jaakar `YouTube Analytics API` search karein aur use bhi **Enable** karein.

---

## Step 3 — OAuth Consent Screen Configure karein
1. Left sidebar me **"APIs & Services"** → **"OAuth consent screen"** par click karein.
2. User Type me **"External"** select karein aur **"Create"** par click karein.
3. Form me ye details bharein:
   - **App name**: `Ghost Creator AI`
   - **User support email**: Apni email address select karein.
   - **Developer contact information**: Apni email address dalein.
4. **"Save and Continue"** par click karein.
5. **Scopes** screen par **"Add or Remove Scopes"** click karein aur neeche diye gaye scopes manually select/search karke add karein:
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`
   - `https://www.googleapis.com/auth/yt-analytics-monetary.readonly`
6. **"Save and Continue"** par click karein.
7. **Test Users** screen par **"Add Users"** click karein aur **apna wahi Google email address dalein jisse aapka YouTube Channel hai** (Kyunki app abhi testing mode me hai, isliye sirf wahi accounts login kar payenge jo yahan Test Users me added hain).
8. **"Save and Continue"** click karke finish karein.

---

## Step 4 — OAuth Desktop Credentials Create karein
1. Left sidebar me **"APIs & Services"** → **"Credentials"** par click karein.
2. Top me **"+ Create Credentials"** → **"OAuth client ID"** select karein.
3. Application Type dropdown me **"Desktop app"** select karein.
4. Name me `Ghost Desktop Client` dalein aur **"Create"** click karein.
5. Ek popup aayega jisme Client ID aur Secret hoga. Wahan **"Download JSON"** button par click karke file download kar lein.

---

## Step 5 — File ko Save karein
1. Jo JSON file download hui hai (uska naam kuch `client_secret_xxxx.json` jaisa hoga), use rename karke bilkul ye naam rakhein:
   ```
   yt_client_secrets.json
   ```
2. Is file ko copy karke apne project folder me daal dein:
   ```
   c:\Users\pc\OneDrive\Desktop\New folder\ghost-creator\yt_client_secrets.json
   ```

---

## Step 6 — App me Connect karein
1. Ghost Creator App ke **Settings** me jayein.
2. Channel card par **🔑 Connect Google** click karein.
3. Browser window khulegi, wahan apna YouTube wala account select karke permissions ko **Allow**/Continue kar dein.
4. Setup complete! Ab aap direct **📊 Sync Analytics** click karke real time dynamic stats aur graph dekh sakte hain.
