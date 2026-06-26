# 🚀 Deployment Guide: Deploy Framey for Free

This guide provides step-by-step instructions to deploy both the backend and frontend of Framey completely free using modern cloud platforms.

## System Components & Services
1. **Database & Storage**: Supabase (Free Tier)
2. **AI APIs**: Groq Cloud (Free / Pay-as-you-go API key)
3. **Backend Service**: Koyeb (Free Tier) or Render (Free Tier)
4. **Frontend Dashboard**: Vercel (Free Tier) or Netlify (Free Tier)

---

## Step 1: Set Up Supabase

1. Go to [Supabase](https://supabase.com/) and create a new project.
2. Once the project is initialized, navigate to the **SQL Editor** from the left sidebar.
3. Click **New query**, paste the entire contents of the [`supabase_setup.sql`](supabase_setup.sql) file located in the root of the project, and click **Run**.
   * This SQL script initializes the `jobs` table, configures Row Level Security (RLS) policies, registers the table for Postgres Realtime updates, creates the public `clips` storage bucket, and applies permissions.
4. Navigate to **Project Settings** -> **API** to retrieve:
   * **Project URL** (corresponds to `VITE_SUPABASE_URL`)
   * **anon/public Key** (corresponds to `VITE_SUPABASE_ANON_KEY`)
   * **service_role/secret Key** (corresponds to `SUPABASE_SERVICE_ROLE_KEY` - keep this secret!)

---

## Step 2: Set Up Groq Cloud

1. Go to [Groq Console](https://console.groq.com/) and register or log in.
2. Navigate to **API Keys** and generate a new API key.
3. Save this key (corresponds to `GROQ_API_KEY`).

---

## Step 3: Deploy the Backend API (Koyeb or Render)

Choose either **Koyeb** or **Render**. Both offer free tiers. Docker deployment is recommended because the project's backend requires `ffmpeg` (which is pre-installed in our `backend/Dockerfile`).

### Option A: Deploy on Koyeb (Recommended - Very Fast)
1. Register/Login on [Koyeb](https://www.koyeb.com/).
2. Click **Create Service** and select **GitHub**.
3. Select your repository.
4. In the configuration:
   * **Builder**: Choose **Docker**
   * **Docker directory**: Set to `/backend` (so it builds using the Dockerfile inside the backend directory)
   * **Exposed Ports**: Port `8000` (HTTP)
   * **App Name / Service Name**: e.g., `framey-backend`
5. Add the following **Environment Variables**:
   * `ENV` = `production`
   * `PORT` = `8000`
   * `USE_CELERY` = `false` *(Instructs the server to use FastAPI's built-in thread pool for tasks, bypassing the need for a Redis server!)*
   * `VITE_SUPABASE_URL` = `<your_supabase_project_url>`
   * `VITE_SUPABASE_ANON_KEY` = `<your_supabase_anon_key>`
   * `SUPABASE_SERVICE_ROLE_KEY` = `<your_supabase_service_role_key>`
   * `GROQ_API_KEY` = `<your_groq_api_key>`
   * `GROQ_LLM_MODEL` = `llama-3.1-8b-instant` *(or `llama-3.3-70b-versatile`)*
6. Click **Deploy**. Note down the deployment URL once live (e.g., `https://<your-service-name>.koyeb.app`).

### Option B: Deploy on Render
1. Register/Login on [Render](https://render.com/).
2. Click **New** -> **Web Service**.
3. Connect your GitHub repository.
4. Set the following settings:
   * **Root Directory**: `backend`
   * **Runtime**: `Docker`
   * **Instance Type**: `Free`
5. Click **Advanced** and add the same environment variables as listed under the Koyeb setup above.
6. Click **Create Web Service**. Note down the deployment URL once live (e.g., `https://<your-service-name>.onrender.com`).

---

## Step 4: Deploy the Frontend (Vercel or Netlify)

### Option A: Deploy on Vercel (Recommended)
1. Register/Login on [Vercel](https://vercel.com/).
2. Click **Add New** -> **Project**.
3. Import your GitHub repository.
4. In the project settings:
   * **Root Directory**: Set to `frontend`
   * **Framework Preset**: **Vite** (automatically detected)
5. Add the following **Environment Variables**:
   * `VITE_SUPABASE_URL` = `<your_supabase_project_url>`
   * `VITE_SUPABASE_ANON_KEY` = `<your_supabase_anon_key>`
   * `VITE_API_BASE` = `<your_deployed_backend_api_url>` *(e.g. `https://framey-backend.koyeb.app` or `https://framey-backend.onrender.com`)*
6. Click **Deploy**.

### Option B: Deploy on Netlify
1. Register/Login on [Netlify](https://www.netlify.com/).
2. Click **Add new site** -> **Import an existing project** -> **GitHub**.
3. Select your repository.
4. Set the build settings:
   * **Base directory**: `frontend`
   * **Build command**: `npm run build`
   * **Publish directory**: `dist`
5. Under **Environment variables**, click **Add variables** and paste the same variables as listed under the Vercel setup above.
6. Click **Deploy site**.

---

## Step 5: Configure CORS on the Backend (Optional)
To lock down security in production:
* Go back to your Backend Web Service configuration (Koyeb or Render).
* Update/add the environment variable `ALLOWED_ORIGINS` and set it to your deployed Frontend URL (e.g., `https://framey-app.vercel.app`).
* Redeploy/restart the backend.
