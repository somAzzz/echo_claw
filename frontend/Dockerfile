FROM node:20-slim

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY . .

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]