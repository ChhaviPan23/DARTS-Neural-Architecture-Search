# -*- coding: utf-8 -*-
"""DA 202 Course Project.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1C8qoJfOC9fC9vs-Z-zUkpoARopHj-TId
"""

import PIL
import matplotlib.pyplot as plt
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms, models
from torchvision.utils import make_grid
import os
import random
import numpy as np
import pandas as pd
import pickle
import time


from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.distributed import init_process_group, destroy_process_group

def ddp_setup():
  init_process_group(backend="nccl")
  torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))

def add_noise(img_tensor, mean=0, std=1.5):
    noise = torch.randn_like(img_tensor) * std + mean
    noisy_img_tensor = img_tensor + noise
    return noisy_img_tensor

class BrainTumorDataset(Dataset):
  def __init__(self, images, labels):
    # images
    self.X = images
    # labels
    self.y = labels

    # Transformation for converting original image array to an image and then convert it to a tensor
    self.transform = transforms.Compose([transforms.ToPILImage(),
        transforms.ToTensor()
    ])

    self.transform1 = transforms.Compose([
        transforms.ToPILImage(),
        transforms.RandomRotation(90),
        transforms.ToTensor()
    ])

    self.transform2 = transforms.Compose([
        transforms.ToPILImage(),
        transforms.RandomRotation(180),
        transforms.ToTensor()
    ])

    self.transform3 = transforms.Compose([
        transforms.ToPILImage(),
        transforms.functional.vflip,
        transforms.ToTensor()
    ])

    self.transform4 = transforms.Compose([
        transforms.ToPILImage(),
        transforms.functional.vflip,
        transforms.ToTensor()
    ])

    self.transform5 = transforms.Compose([
        transforms.ToTensor(),
        transforms.Lambda(lambda x: add_noise(x))
    ])


  def __len__(self):
    # return length of image samples
    return 6*len(self.X)

  def __getitem__(self, idx):
    idx = idx//6
    r = idx%6
    if(r==0):
      data = self.transform(self.X[idx])
    if(r==1):
      data = self.transform1(self.X[idx])
    if(r==2):
      data = self.transform2(self.X[idx])
    if(r==3):
      data = self.transform3(self.X[idx])
    if(r==4):
      data = self.transform4(self.X[idx])
    if(r==5):
      data = self.transform5(self.X[idx])

    # print(data.shape)
    # data=data.swapaxes(0,1)
    # data=data.swapaxes(1,2)
    # print(data.shape)
    labels = torch.zeros(3, dtype=torch.float32)
    labels[int(self.y[idx])-1] = 1.0

    return data,labels

file = open("training_data.pickle",'rb')
training_data = pickle.load(file)
file.close()

Xt = []
yt = []
features = None
labels = None
label = []

for features,labels in training_data:
  Xt.append(features)
  yt.append(labels)

from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(Xt, yt, test_size=0.32, shuffle=True)
X_valid, X_test, y_valid, y_test = train_test_split(X_test, y_test, test_size=0.5, shuffle=True)

train_set = BrainTumorDataset(X_train, y_train)
valid_set = BrainTumorDataset(X_valid, y_valid)
test_set = BrainTumorDataset(X_test, y_test)

train_gen = DataLoader(train_set, batch_size=16, shuffle=True, pin_memory=True,num_workers=2)
valid_gen = DataLoader(valid_set, batch_size=16, shuffle=True, pin_memory=True, num_workers=2)
test_gen = DataLoader(test_set, batch_size=16, shuffle=True, pin_memory=True, num_workers=2)

train_gen_help = DataLoader(train_set, batch_size=16, shuffle=True, pin_memory=True,num_workers=2)



"""# **Fine Tuning**"""

import torchvision

model = torch.nn.Sequential(torchvision.models.vgg19(weights="IMAGENET1K_V1").to(torch.device("cuda:0")), torch.nn.Linear(1000, 3))
model.to(torch.device("cuda:0"))

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

def pretrained_feature_maps(pretrained_model,train_gen_help)
  conv_weights = []
  conv_layers = []
  total_conv_layers = 0

  for module in pretrained_model.features.children():
      if isinstance(module, nn.Conv2d):
          total_conv_layers += 1
          conv_weights.append(module.weight)
          conv_layers.append(module)

  print(f"Total convolution layers: {total_conv_layers}")

  pretrained_model = pretrained_model.to(device)
  input_image = next(iter(train_gen_help))
  input_image = input_image.unsqueeze(0)
  input_image = input_image.to(device)

  feature_maps = []
  layer_names = []
  for layer in conv_layers:
      input_image = layer(input_image)
      feature_maps.append(input_image)
      layer_names.append(str(layer))

  print("\nFeature maps shape")
  for feature_map in feature_maps:
      print(feature_map.shape)

  processed_feature_maps = []  # List to store processed feature maps
  for feature_map in feature_maps:
      feature_map = feature_map.squeeze(0)  # Remove the batch dimension
      mean_feature_map = torch.sum(feature_map, 0) / feature_map.shape[0]  # Compute mean across channels
      processed_feature_maps.append(mean_feature_map.data.cpu().numpy())


  # Display processed feature maps shapes
  print("\n Processed feature maps shape")
  for fm in processed_feature_maps:
    print(fm.shape)

  # Plot the feature maps
  fig = plt.figure(figsize=(30, 50))
  for i in range(len(processed_feature_maps)):
    ax = fig.add_subplot(5, 4, i + 1)
    ax.imshow(processed_feature_maps[i])
    ax.axis("off")
    ax.set_title(layer_names[i].split('(')[0], fontsize=30)

def loss_batch(model,loss_func,xb,yb,opt = None):
  xb, yb = xb.to(device), yb.to(device)
  loss = loss_func()
  loss1=loss(model(xb),yb)

  if opt is not None:
    loss1.backward()
    opt.step()
    opt.zero_grad()

  return loss1.item(), len(xb)

def fit(epochs,model,loss_func,opt,train_dl,valid_dl):
  for epoch in range(epochs):
    model.train()
    for xb,yb in train_dl:
      xb, yb = xb.to(device), yb.to(device)
      loss_batch(model,loss_func,xb,yb,opt)

    model.eval()
    with torch.no_grad():
      losses1,nums1 = zip(*[loss_batch(model,loss_func,xb,yb) for xb,yb in train_dl])
      losses,nums = zip(*[loss_batch(model,loss_func,xb,yb) for xb,yb in valid_dl])

    val_loss = np.sum(np.multiply(losses,nums))/np.sum(nums)
    train_loss = np.sum(np.multiply(losses1,nums1))/np.sum(nums1)

    print("train ", epoch, train_loss)
    print("val",epoch,val_loss)

import argparse

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('learning_rate', type=float,
                        help='lr')

    return parser.parse_args()

def main():
  args = parse_args()
  pretrained_feature_maps(model,train_gen_help)
  opt = torch.optim.Adam(model.parameters(),lr = args.learning_rate,weight_decay = 0.1)
  fit(epochs=50,model=model,loss_func=torch.nn.CrossEntropyLoss,opt=opt,train_dl=train_gen,valid_dl=valid_gen)
  torch.save(model.state_dict(), 'weights_trained.pth')
  pretrained_feature_maps(model,train_gen_help)

if __name__ == '__main__':
    main()