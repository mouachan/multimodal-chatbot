# Multimodal Chatbot Demo

![screenshot.png](img/screenshot.png)

[Link to interactive presentation](https://interact.redhat.com/share/mKJcep7CgKLEzhOgrPRC)

Features:

- Patternfly 6 based UI, using the Chatbot component, with support for multimodal models

## Application

### Backend

The [app backend](./app/backend/) is a simple FastAPI application that handles all the communications with the models servers and the client.

The configuration is set in a single [config.json](./app/backend/config.json.example) file, which makes it easier to be kept in a Secret mounted at runtime for the [deployment](./app/deployment/deployment.yaml) on OpenShift.

### Frontend

This is a [Patternfly 6](https://www.patternfly.org/) application, connected to the backend through  Websocket to receive and display the content streamed by the backend.

### Container Image

You have two options for the container image:

**Option 1: Use the pre-built public image**
- The application container image is available at [https://quay.io/repository/rh-aiservices-bu/multimodal-chatbot](https://quay.io/repository/rh-aiservices-bu/multimodal-chatbot).

**Option 2: Build and push your own image**

The application uses a Containerfile (located in `app/Containerfile`) to build the container image. To build and push the image to your registry:

1. **Build the image** (for amd64 architecture):
   ```bash
   cd app
   podman build --platform linux/amd64 --ulimit nofile=10000:10000 -t quay.io/<your-username>/multimodal-chatbot:latest .
   ```
   
   **Note:** Replace `<your-username>` with your Quay.io username or use your preferred registry.

2. **Push to Quay.io** (or your preferred registry):
   ```bash
   podman push quay.io/<your-username>/multimodal-chatbot:latest
   ```

   **Note:** Make sure you're logged in to Quay.io:
   ```bash
   podman login quay.io
   ```

3. **Make the image public** (if using Quay.io):
   - Go to your repository on Quay.io
   - Navigate to Settings → Make Public

### Deployment on OpenShift

- Use the pre-built public image (see above) or build and push your own image to your registry.
- Deployment files examples are available in the [Deployment](./app/deployment/) folder.
- An example configuration file for accessing the models and vector database is available [here](./app/backend/config.json.example). Once modified with your own values, it must be created as a Secret with:

    ```bash
    oc create secret generic multimodal-chatbot --from-file=config.json=config.json -n <your-namespace>
    ```

- Update the `deployment.yaml` with your image registry and tag before deploying:
  ```bash
  oc apply -f app/deployment/deployment.yaml
  oc apply -f app/deployment/service.yaml
  oc apply -f app/deployment/route.yaml
  ```
