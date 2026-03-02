FROM nginx:1.25-alpine

# Install nginx-module-headers-more for server header removal
RUN apk add --no-cache nginx-mod-http-headers-more

# Copy configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

# Create SSL directory for certificates
RUN mkdir -p /etc/ssl/certs /etc/ssl/private

# Expose ports
EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]

