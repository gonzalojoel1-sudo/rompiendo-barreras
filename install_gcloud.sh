#!/bin/bash
echo "Descargando Google Cloud CLI..."
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm.tar.gz

echo "Extrayendo archivos..."
tar -xf google-cloud-cli-darwin-arm.tar.gz -C /Users/joelpacheco
rm google-cloud-cli-darwin-arm.tar.gz

echo "Instalando..."
/Users/joelpacheco/google-cloud-sdk/install.sh --quiet --path-update true

echo "¡Instalación completada! Por favor, reinicia la ventana de tu terminal o IDE para que los cambios surtan efecto."
