FROM node:20-alpine

WORKDIR /app

# Installer les dépendances
COPY package*.json ./
RUN npm install

# Copier le code
COPY . .

# Lancer en mode développement
CMD ["npm", "run", "dev"]
