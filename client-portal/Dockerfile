# <dockerfile name="client-portal" stack="React (Vite) -> Nginx">
#   The CUSTOMER web portal — a second, self-contained app that runs alongside
#   the company CRM (frontend/) on the same server. Two stages: build the static
#   site with Vite, then serve it with Nginx which also proxies /api to the shared
#   backend. REACT_APP_BACKEND_URL is left empty so the app calls the API at
#   same-origin "/api" (nginx proxies it) — no CORS, no hard-coded backend URL.
# </dockerfile>

# --- stage 1: build ---
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json ./
RUN npm install --legacy-peer-deps --no-audit --no-fund

COPY . .
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN npm run build

# --- stage 2: serve ---
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
