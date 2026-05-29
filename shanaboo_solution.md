```diff
--- a/deploy/Dockerfile
+++ b/deploy/Dockerfile
@@ -0,0 +1,25 @@
+# Use an official Python runtime as a parent image
+FROM python:3.10-slim
+
+# Set the working directory in the container
+WORKDIR /app
+
+# Copy the current directory contents into the container at /app
+COPY . /app
+
+# Install any needed packages specified in requirements.txt
+RUN pip install --no-cache-dir -r requirements.txt
+
+# Make port 5000 available to the world outside this container
+EXPOSE 5000
+
+# Define environment variable
+ENV NAME World
+
+# Run app.py when the container launches
+CMD ["gunicorn", "-b", "0.0.0.0:5000", "app.app:app"]
+
+--- a/deploy/docker-compose.yml
+++ b/deploy/docker-compose.yml
@@ -1,11 +1,45 @@
 version: '3.8'
 
 services:
+  web:
+    build: .
+    command: gunicorn -b 0.0.0.0:5000 app.app:app
+    volumes:
+      - .:/app
+    ports:
+      - "5000:5000"
+    depends_on:
+      - db
+      - redis
+    environment:
+      - FLASK_ENV=production
+      - DATABASE_URL=postgresql://postgres:password@db:5432/finmind
+      - REDIS_URL=redis://redis:6379/0
+
   db:
     image: postgres:13
     environment:
       POSTGRES_DB: finmind
       POSTGRES_USER: postgres
       POSTGRES_PASSWORD: password
+    volumes:
+      - db_data:/var/lib/postgresql/data
+
+  redis:
+    image: redis:6
+    volumes:
+      - redis_data:/data
+
+volumes:
+  db_data:
+  redis_data:
+
+--- a/deploy/kubernetes/deployment.yaml
+++ b/deploy/kubernetes/deployment.yaml
@@ -0,0 +1,54 @@
+apiVersion: apps/v1
+kind: Deployment
+metadata:
+  name: finmind-deployment
+spec:
+  replicas: 3
+  selector:
+    matchLabels:
+      app: finmind
+  template:
+    metadata:
+      labels:
+        app: finmind
+    spec:
+      containers:
+      - name: finmind
+        image: your-docker-repo/finmind:latest
+        ports:
+        - containerPort: 5000
+        env:
+        - name: FLASK_ENV
+          value: "production"
+        - name: DATABASE_URL
+          value: "postgresql://postgres:password@finmind-db:5432/finmind"
+        - name: REDIS_URL
+          value: "redis://finmind-redis:6379/0"
+        livenessProbe:
+          httpGet:
+            path: /health
+            port: 5000
+          initialDelaySeconds: 30
+          periodSeconds: 10
+        readinessProbe:
+          httpGet:
+            path: /health
+            port: 5000
+          initialDelaySeconds: 5
+          periodSeconds: 10
+
+--- a/deploy/kubernetes/service.yaml
+++ b/deploy/kubernetes/service.yaml
@@ -0,0 +1,15 @@
+apiVersion: v1
+kind: Service
+metadata:
+  name: finmind-service
+spec:
+  selector:
+    app: finmind
+  ports:
+    - protocol: TCP
+      port: 80
+      targetPort: 5000
+  type: LoadBalancer
+
+--- a/deploy/kubernetes/hpa.yaml
+++ b/deploy/kubernetes/hpa.yaml
@@ -0,0 +1,12 @@
+apiVersion: autoscaling/v2
+kind: HorizontalPodAutoscaler
+metadata:
+  name: finmind-hpa
+spec:
+  scaleTargetRef:
+    apiVersion: apps/v1
+    kind: Deployment
+    name: finmind-deployment
+  minReplicas: 1
+  maxReplicas: 10
+  metrics:
+  - type: Resource
+    resource:
+      name: cpu
+      target:
+        type: Utilization
+        averageUtilization: 50
+
+--- a/deploy/kubernetes/ingress.yaml
+++ b/deploy/kubernetes/ingress.yaml
@@ -0,0 +1,20 @@
+apiVersion: networking.k8s.io/v1
+kind: Ingress
+metadata:
+  name: finmind-ingress
+  annotations:
+    nginx.ingress.kubernetes.io/rewrite-target: /
+spec:
+  tls:
+  - hosts:
+    - finmind.example.com
+    secretName: finmind-tls
+  rules:
+  - host: finmind.example.com
+    http:
+      paths:
+      - path: /
+        pathType: Prefix
+        backend:
+          service:
+            name: finmind-service
+            port:
+              number: 80
+
+--- a/deploy/kubernetes/redis-deployment.yaml
+++ b/deploy/kubernetes/redis-deployment.yaml
@@ -0,0 +1,24 @@
+apiVersion: apps/v1
+kind: Deployment
+metadata:
+  name: finmind-redis
+spec:
+  replicas: 1
+  selector:
+    matchLabels:
+      app: finmind-redis
+  template:
+    metadata:
+      labels:
+        app: finmind-redis
+    spec:
+      containers:
+      - name: redis
+        image: redis:6
+        ports:
+        - containerPort: 6379
+        volumeMounts:
+        - name: redis-storage
+          mountPath: /data
+      volumes:
+      - name: redis-storage
+        emptyDir: {}
+
+--- a/deploy/kubernetes/redis-service.yaml
+++ b/deploy/kubernetes/redis-service.yaml
@@ -0,0 +1,13 @@
+apiVersion: v1
+kind: Service
+metadata:
+  name: finmind-redis
+spec:
+  selector:
+    app: finmind-redis
+  ports:
+    - protocol: TCP
+      port: 6379
+      targetPort: 6379
+
+--- a