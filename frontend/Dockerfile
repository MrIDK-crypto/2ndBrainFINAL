# Frontend Dockerfile for Cloud Run
# Multi-stage build for smaller image

# Stage 1: Dependencies
FROM node:20-alpine AS deps
WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install ALL dependencies (including dev for build)
RUN npm ci

# Stage 2: Build
FROM node:20-alpine AS builder
WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Accept build argument for API URL
ARG NEXT_PUBLIC_API_URL=https://secondbrain-backend2.onrender.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Build the application
RUN npm run build

# Stage 3: Production
FROM node:20-alpine AS runner
WORKDIR /app

# Set environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# HOSTNAME must be 0.0.0.0 to accept connections from outside the container
ENV HOSTNAME="0.0.0.0"

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built application
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Set ownership
USER nextjs

# Expose port (Render sets PORT dynamically)
EXPOSE 3000

# Start the application
CMD ["node", "server.js"]
