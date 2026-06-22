# <dockerfile name="frontend" stack="React (CRA 5 + CRACO) -> Nginx">
#   Two stages: (1) build the static site with Node, (2) serve it with Nginx
#   which also proxies /api to the backend. REACT_APP_BACKEND_URL is left empty
#   on purpose so the app calls the API at same-origin "/api".
# </dockerfile>

# --- stage 1: build ---
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json ./
# react 19 + react-scripts 5 have a few peer-dep warnings; legacy-peer-deps
# keeps the install reliable.
RUN npm install --legacy-peer-deps

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
