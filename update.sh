#!/usr/bin/env bash

# Pulls the latest changes and restarts the service

echo "Pull latest version..."
git pull

echo "Update systemctl daemon..."
sudo systemctl daemon-reload

echo "Restart RPiFanControl..."
sudo systemctl restart RPiFanControl.service
