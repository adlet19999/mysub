FROM node:20-alpine

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_API_BASE=/api/v1
ARG NEXT_PUBLIC_API_BASE_URL=/api/v1
ARG NEXT_PUBLIC_TENANT_SLUG=public

ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE} \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_TENANT_SLUG=${NEXT_PUBLIC_TENANT_SLUG}

RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start"]