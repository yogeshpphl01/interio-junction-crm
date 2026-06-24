# <dockerfile name="frontend" stack="React (CRA 5 + CRACO) -> Nginx">
#   Two stages: (1) build the static site with Node, (2) serve it with Nginx
#   which also proxies /api to the backend. REACT_APP_BACKEND_URL is left empty
#   on purpose so the app calls the API at same-origin "/api".
# </dockerfile>

# --- stage 1: build ---
FROM node:20-alpine AS build
WORKDIR /app

# CI=false so ESLint warnings don't fail the production build; no sourcemaps
# keeps the build lighter/faster on a small VPS.
ENV CI=false
ENV GENERATE_SOURCEMAP=false

COPY package.json ./
# This is a YARN project: package.json has a "resolutions" block + a
# packageManager:yarn field, and yarn honours those pins while npm ignores them
# (using npm here is what broke the ajv dependency). So install with yarn.
RUN yarn install --network-timeout 600000

COPY . .
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN yarn build

# --- stage 2: serve ---
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
