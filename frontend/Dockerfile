FROM node:20-slim

WORKDIR /app

COPY package.json ./
# Generates package-lock.json on first run if you haven't committed one yet.
RUN npm install

COPY . .

EXPOSE 3000

# Dev server for the learning demo. For production: `npm run build && npm start`.
CMD ["npm", "run", "dev"]
