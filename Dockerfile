FROM mcr.microsoft.com/playwright:v1.52.0-noble

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --production

COPY src/ src/
COPY skill/ skill/

EXPOSE 3000

CMD ["node", "src/server.js"]
