import torch
import torchvision
from tqdm import tqdm
from torch import nn, optim
from torchmetrics.image import PeakSignalNoiseRatio, StructuralSimilarityIndexMeasure
from torchmetrics.image.fid import FrechetInceptionDistance
from torchmetrics.image.lpip import LearnedPerceptualImagePatchSimilarity
from torchmetrics.image.inception import InceptionScore
import matplotlib.pyplot as plt
from torchvision import transforms
from torchvision.datasets import ImageFolder, MNIST
from torch.autograd import Variable
import pandas as pd
import numpy as np
import torch.nn.functional as F
from numpy import cov
from numpy import trace
from numpy import iscomplexobj
from numpy.random import random
from scipy.linalg import sqrtm
import heapq

import time
start_time = time.time()

batch_size_train = 64
batch_size_attack=1
batch_size_test = 1
gan_batch_size = 32
batch_size_train_attack=1
#batch_size_train=1
## GAN variables
num_epochs = 25
n_critic = 5
display_step = 25

transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize([0.5], [0.5])
])
train_loader = torch.utils.data.DataLoader(
  torchvision.datasets.MNIST('/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/data', train=True, download=True,
                             transform=torchvision.transforms.Compose([
                               torchvision.transforms.ToTensor(),
                               torchvision.transforms.Normalize(
                                 (0.1307,), (0.3081,))
                             ])),
  batch_size=batch_size_train, shuffle=True)
attack_test_loader = torch.utils.data.DataLoader(
  torchvision.datasets.MNIST('/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/data', train=True, download=True,
                             transform=torchvision.transforms.Compose([
                               torchvision.transforms.ToTensor(),
                               torchvision.transforms.Normalize(
                                 (0.1307,), (0.3081,))
                             ])),
  batch_size=batch_size_train_attack, shuffle=True)

test_loader = torch.utils.data.DataLoader(
  torchvision.datasets.MNIST('/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/data', train=False, download=True,
                             transform=torchvision.transforms.Compose([
                               torchvision.transforms.ToTensor(),
                               torchvision.transforms.Normalize(
                                 (0.1307,), (0.3081,))
                             ])),
  batch_size=batch_size_test, shuffle=True)
data_loader = torch.utils.data.DataLoader(MNIST('data', train=True, download=True, transform=transform),
                                          batch_size=gan_batch_size, shuffle=True)
'''
attack_loader = torch.utils.data.DataLoader(
  torchvision.datasets.CIFAR10('/vast/home/sdibbo/def_ddlc/data', train=True, download=True,
                             transform=torchvision.transforms.Compose([
                               torchvision.transforms.ToTensor(),
                               torchvision.transforms.Normalize(
                                 (0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
                             ])),
  batch_size=batch_size_attack, shuffle=True)
'''  
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # use gpu if available
class Discriminator(nn.Module):
    def __init__(self):
        super().__init__()
        
        self.label_emb = nn.Embedding(10, 10)
        
        self.model = nn.Sequential(
            nn.Linear(794, 1024),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Dropout(0.3),
            nn.Linear(1024, 512),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Dropout(0.3),
            nn.Linear(512, 256),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Dropout(0.3),
            nn.Linear(256, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x, labels):
        x = x.view(x.size(0), 784)
        c = self.label_emb(labels)
        x = torch.cat([x, c], 1)
        out = self.model(x)
        return out.squeeze()
    
class Generator(nn.Module):
    def __init__(self):
        super().__init__()
        
        self.label_emb = nn.Embedding(10, 10)
        
        self.model = nn.Sequential(
            nn.Linear(110, 256),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(256, 512),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(512, 1024),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(1024, 784),
            nn.Tanh()
        )
    
    def forward(self, z, labels):
        z = z.view(z.size(0), 100)
        c = self.label_emb(labels)
        x = torch.cat([z, c], 1)
        out = self.model(x)
        print(x.shape)
        return out.view(x.size(0), 28, 28)
        
generator = Generator().to(device)
discriminator = Discriminator().to(device)

d_optimizer = torch.optim.Adam(discriminator.parameters(), lr=1e-4)
g_optimizer = torch.optim.Adam(generator.parameters(), lr=1e-4)
cost = torch.nn.CrossEntropyLoss()

def generator_train_step(batch_size, discriminator, generator, g_optimizer, cost):
    g_optimizer.zero_grad()
    z = Variable(torch.randn(batch_size, 100)).cuda()
    fake_labels = Variable(torch.LongTensor(np.random.randint(0, 10, batch_size))).cuda()
    fake_images = generator(z, fake_labels)
    validity = discriminator(fake_images, fake_labels)
    g_loss = cost(validity, Variable(torch.ones(batch_size)).cuda())
    g_loss.backward()
    g_optimizer.step()
    return g_loss.item()

def discriminator_train_step(batch_size, discriminator, generator, d_optimizer, cost, real_images, labels):
    d_optimizer.zero_grad()

    # train with real images
    real_validity = discriminator(real_images, labels)
    real_loss = cost(real_validity, Variable(torch.ones(batch_size)).cuda())
    
    # train with fake images
    z = Variable(torch.randn(batch_size, 100)).cuda()
    fake_labels = Variable(torch.LongTensor(np.random.randint(0, 10, batch_size))).cuda()
    fake_images = generator(z, fake_labels)
    fake_validity = discriminator(fake_images, fake_labels)
    fake_loss = cost(fake_validity, Variable(torch.zeros(batch_size)).cuda())
    
    d_loss = real_loss + fake_loss
    d_loss.backward()
    d_optimizer.step()
    return d_loss.item()

def Average(lst):
  return sum(lst) / len(lst)
all_d_loss=[]
for epoch in range(num_epochs):
    print('Starting epoch {}...'.format(epoch), end=' ')
    for i, (images, labels) in enumerate (tqdm(data_loader)):
        
        step = epoch * len(data_loader) + i + 1
        real_images = Variable(images).cuda()
        labels = Variable(labels).cuda()
        generator.train()
        
        d_loss = 0
        for _ in range(n_critic):
            d_loss = discriminator_train_step(len(real_images), discriminator,
                                              generator, d_optimizer, cost,
                                              real_images, labels)
        

        g_loss = generator_train_step(gan_batch_size, discriminator, generator, g_optimizer, cost)
        
       # writer.add_scalars('scalars', {'g_loss': g_loss, 'd_loss': (d_loss / n_critic)}, step)  
        
        if step % display_step == 0:
            generator.eval()
            z = Variable(torch.randn(9, 100)).cuda()
            labels = Variable(torch.LongTensor(np.arange(9))).cuda()
            sample_images = generator(z, labels).unsqueeze(1)
            #grid = make_grid(sample_images, nrow=3, normalize=True)
            #writer.add_image('sample_image', grid, step)
    all_d_loss.append(d_loss)
        
norm_d_loss=Average(all_d_loss)
print('GAN Training is Done!')
def generate_img(generator, digit):
    z = Variable(torch.randn(1, 100)).cuda()
    label = torch.LongTensor([digit]).cuda()
    img = generator(z, label).data.cpu()
    img = 0.5 * img + 0.5
    return img
class GaussianNoise(nn.Module):
    def __init__(self, sigma=0.5, is_relative_detach=True):
        super().__init__()
        self.sigma = sigma
        self.is_relative_detach = is_relative_detach
        self.noise = torch.tensor(1)

    def forward(self, x):
        if self.training and self.sigma != 0:
            scale = self.sigma * x if self.is_relative_detach else self.sigma * x
            sampled_noise = self.noise * scale
            x = x + sampled_noise
        return x
class SplitNN(nn.Module):
  def __init__(self):
    super(SplitNN, self).__init__()
    self.first_part = nn.Sequential(
       GaussianNoise(),
                           nn.Linear(28, 500),
                           nn.ReLU(),
                         )
    self.second_part = nn.Sequential(
       GaussianNoise(),
                           nn.Linear(500, 500),
                           nn.ReLU(),
                           nn.Linear(500, 28),
                           nn.ReLU(), 
                           nn.Linear(28, 500),                        )
    self.third_part = nn.Sequential(
                           nn.Linear(1*28*500, 10),
                           #scancel nn.Softmax(dim=-1),
                         )

  def forward(self, x):
     #x=x.view(-1,32*32*3)
    x=self.first_part(x)
    #print(x.shape)
    #x = torch.flatten(x, 1) # flatten all dimensions except batch
    #print(x.shape)
    x=self.second_part(x)
    #print(x.shape)
    x = x.view(-1, 1*28*500)
    x=self.third_part(x)
    return x

'''
class SplitNN(nn.Module):
  def __init__(self):
    super(SplitNN, self).__init__()
    self.first_part = nn.Sequential(
                           nn.Linear(3*32*32,512),
                           nn.ReLU(),
                           #nn.Dropout(0.25),
                           #nn.Linear(2048,512),
                           #nn.ReLU(),
                           #nn.Dropout(0.25),
                           #nn.Linear(1024,512),
                           #nn.ReLU(),
                           #nn.Dropout(0.25),
                         )
    self.second_part = nn.Sequential(
                           nn.Linear(512, 256),
                           nn.ReLU(),
                           #nn.Dropout(0.25),
                           nn.Linear(256, 10),
                           #nn.Softmax(dim=-1),
                         )

  def forward(self, x):
    x=x.view(-1,32*32*3)
    x=self.first_part(x)
    #print(x.shape)
    #x = torch.flatten(x, 1) # flatten all dimensions except batch
    #x = x.view(-1, 48000)
    #print(x.shape)
    x=self.second_part(x)
    return x
'''    
target_model = SplitNN().to(device=device)

class Attacker(nn.Module):
  def __init__(self):
    super(Attacker, self).__init__()
    self.layers= nn.Sequential(
                      nn.Linear(500, 800),
                      nn.ReLU(),
                      nn.Linear(800, 28),
                    )
 
  def forward(self, x):
    return self.layers(x)
'''
class Attacker(nn.Module):
  def __init__(self):
    super(Attacker, self).__init__()
    self.layers= nn.Sequential(
                      nn.Linear(512, 800),
                      nn.ReLU(),
                      nn.Linear(800, 32*32*3),
                    )
 
  def forward(self, x):
    return self.layers(x)  
'''    
attack_model = Attacker().to(device=device)
#optimiser = optim.Adam(target_model.parameters(), lr=1e-4)
optimiser=torch.optim.SGD(target_model.parameters(),lr=0.001,momentum=0.9)
cost = torch.nn.CrossEntropyLoss()
def Average(lst):
    return sum(lst) / len(lst)
# calculate frechet inception distance
def calculate_fid(act1, act2):
 # calculate mean and covariance statistics
 mu1, sigma1 = act1.mean(axis=0), cov(act1, rowvar=False)
 mu2, sigma2 = act2.mean(axis=0), cov(act2, rowvar=False)
 # calculate sum squared difference between means
 ssdiff = np.sum((mu1 - mu2)**2.0)
 # calculate sqrt of product between cov
 covmean = sqrtm(sigma1.dot(sigma2))
 # check and correct imaginary numbers from sqrt
 if iscomplexobj(covmean):
  covmean = covmean.real
 # calculate score
 fid = ssdiff + trace(sigma1 + sigma2 - 2.0 * covmean)
 fid=fid/1000.00
 return fid

def poincare_loss(outputs, targets, xi=1e-4):
    # Normalize logits
    u = outputs / torch.norm(outputs, p=1, dim=-1).unsqueeze(0)
    # Create one-hot encoded target vector
    v = torch.clip(
        torch.eye(outputs.shape[-1], device=outputs.device)[targets] - xi, 0,
        1)
    v = v.to(u.device)
    # Compute squared norms
    u_norm_squared = torch.norm(u, p=2, dim=-1)**2
    v_norm_squared = torch.norm(v, p=2, dim=-1)**2
    diff_norm_squared = torch.norm(u - v, p=2, dim=-1)**2
    # Compute delta
    delta = 2 * diff_norm_squared / ((1 - u_norm_squared) *
                                     (1 - v_norm_squared))
    # Compute distance
    loss = torch.arccosh(1 + delta)
    return loss

def target_train(train_loader, target_model, optimiser):
    target_model.train()
    size = len(train_loader.dataset)
    correct = 0
    total_loss=[]
    for batch, (X, Y) in enumerate(tqdm(train_loader)):
        #print(target_model)
        X, Y = X.to(device=device), Y.to(device)
        #print(X.shape)
        target_model.zero_grad()
        pred = target_model(X)
        gan_loss=[]
        for i in range(Y[0]):
            label=Y[i]
            recreated_data=generate_img(generator, label)
            print(recreated_data.shape)
            recon_img=recreated_data[0]/ 1 + 0.5
            #print(pred.shape, Y.shape)
            #recon_img=torch.permute(recon_img, (2,1, 0))
            recon_img=recon_img.unsqueeze(0).repeat(64, 1, 1, 1)
            #print(recon_img.shape)
            recon_img=recon_img.to(device=device)
            pred2 = target_model(recon_img)
            loss2 = cost(pred2[0], Y[i])
            if loss2.item()==0:
               loss.item=0.00001
            #print(loss2)
            _, output2 = torch.max(pred2[0], 0)
            correct+= (output2 == Y[i]).sum().item()
            gan_loss.append(loss2.item())
        #print(gan_loss)
        if not gan_loss:
           gan_loss.append(0.00001)
        loss_other=Average(gan_loss)    
        loss = cost(pred, Y)
        loss=loss+loss_other
        loss.backward()
        optimiser.step()
        _, output = torch.max(pred, 1)
        correct+= (output == Y).sum().item()
        total_loss.append(loss.item())
        #batch_count+=batch
        #correct += (pred.argmax(1)==Y).type(torch.float).sum().item()

    correct /= (2*size)
    loss= sum(total_loss)/batch
    result_train=100*correct
    print(f'\nTraining Performance:\nacc: {(100*correct):>0.1f}%, avg loss: {loss:>8f}\n')
    
    return loss, result_train

def clip_images(imgs):
    lower_limit = torch.tensor(-1.0).float().to(imgs.device)
    upper_limit = torch.tensor(1.0).float().to(imgs.device)
    imgs = torch.where(imgs > upper_limit, upper_limit, imgs)
    imgs = torch.where(imgs < lower_limit, lower_limit, imgs)
    return imgs

#test_loader, target_model, attack_model, optimiser
def attack_train(test_loader, target_model, attack_model, optimiser):
    model = SplitNN()
#for data, targets in enumerate(tqdm(train_loader)):
    generator.train()
    size = len(train_loader.dataset)
    correct = 0
    total_loss=[]
    #optimiser=torch.optim.Adam(generator.parameters(), lr=1e-4)
    for batch, (X, Y) in enumerate(tqdm(test_loader)):
    # Reset gradients
        X, Y = X.to(device=device), Y.to(device=device)
        optimiser.zero_grad()
        pred = target_model(X)
        gan_loss=[]
        for i in range(10):
            label=Y[0]
            recreated_data=generate_img(generator, label)
            #print(recreated_data.shape)
            #recon_img=torch.permute(recreated_data[0]/ 2 + 0.5, (1,2, 0))
            #print(pred.shape, Y.shape)
            #recon_img=torch.permute(recon_img, (2,1, 0))
            #recon_img=recon_img.unsqueeze(0).repeat(1, 1, 1, 1)
            #print(recon_img.shape)
            recon_img=recreated_data
            recon_img=recon_img.to(device=device)
            recon_img=clip_images(recon_img)
            transform1=torchvision.transforms.Compose([torchvision.transforms.ToPILImage(),torchvision.transforms.RandomResizedCrop(size=(28, 28),
                                scale=(0.5, 0.9),
                                ratio=(0.8, 1.2),
                                antialias=True),torchvision.transforms.ToTensor()])
            transform2=torchvision.transforms.Compose([torchvision.transforms.ToPILImage(),torchvision.transforms.RandomHorizontalFlip(0.5),torchvision.transforms.ToTensor()])
            
            transform3=torchvision.transforms.Compose([torchvision.transforms.ToPILImage(),torchvision.transforms.RandomHorizontalFlip(0.1),torchvision.transforms.ToTensor()])
            recreated_data1=transform1(recon_img)
            recreated_data2=transform2(recon_img)
            recreated_data3=transform3(recon_img)
            recon_img1=recreated_data1.unsqueeze(0).repeat(1, 1, 1, 1)
            recon_img2=recreated_data2.unsqueeze(0).repeat(1, 1, 1, 1)
            recon_img3=recreated_data3.unsqueeze(0).repeat(1, 1, 1, 1)


            outputs1 =  target_model(recon_img1.to(device=device)) # obtain logits
            outputs2 =  target_model(recon_img2.to(device=device)) # obtain logits
            outputs3=  target_model(recon_img3.to(device=device)) # obtain logits


            pred2 = target_model(recon_img.unsqueeze(0).repeat( 1, 1, 1, 1))
            target_loss1 = poincare_loss(
            outputs1[0], Y[0]).mean()
            #print(target_loss)
            loss2 = cost(pred2[0], Y[0])
            if target_loss1.item()==0:
               loss.item=0.00001
            #print(loss2)
            _, output2 = torch.max(pred2[0], 0)
            correct+= (output2 == Y[0]).sum().item()
            gan_loss.append(target_loss1.item())
        #print(gan_loss)
        if not gan_loss:
           gan_loss.append(0.00001)
        loss = cost(pred, Y)
        target_loss1 = poincare_loss(
         outputs1[0], Y[0]).mean()
        target_loss2 = poincare_loss(
            outputs2[0], Y[0]).mean()
        target_loss3 = poincare_loss(
            outputs3[0], Y[0]).mean()
        loss=target_loss1+target_loss2+ target_loss3+norm_d_loss
        #print(loss)
        loss.backward()
        optimiser.step()
        _, output = torch.max(pred, 1)
        correct+= (output == Y).sum().item()
        total_loss.append(loss.item())
        
    correct /= (2*size)
    loss= sum(total_loss)/batch
    result_train=100*correct
    print(f'\nTraining Performance:\nacc: {(100*correct):>0.1f}%, avg loss: {loss:>8f}\n')
    
    return loss, result_train



def target_utility(test_loader, target_model, batch_size=1):
    size = len(test_loader.dataset)
    target_model.eval()
    test_loss, correct = 0, 0
    correct = 0
    counter_a=0
    total=0
    #with torch.no_grad():
    for batch, (X, Y) in enumerate(tqdm(test_loader)):
        X, Y = X.to(device=device), Y.to(device)
        X.requires_grad = True
        #X= X.view(-1,32*32*3)
        pred = target_model(X)
        counter_a=counter_a+1
        #test_loss += cost(pred, Y).item()
        #correct += (pred.argmax(1)==Y).type(torch.float).sum().item()


        #data, target = data.to(device), target.to(device)
       
        # Set requires_grad attribute of tensor. Important for Attack
        total += Y.size(0)
        # Forward pass the data through the model
        init_pred = pred.max(1, keepdim=True)[1] # get the index of the max log-probability

        if init_pred.item() == Y.item():
            correct += 1


    # Calculate final accuracy for this epsilon
    final_acc = correct/float(total)
    print(f"Target Model Accuracy = {correct} / {total} = {final_acc}")

    # Return the accuracy and an adversarial example
    return final_acc 



def attack_test(train_loader, target_model, attack_model):
    model = SplitNN()
    psnr_lst, ssim_lst, fid_lst=[], [], []
    correct=0
    attack_correct=0
    total=0
    for batch, (X, Y) in enumerate(tqdm(train_loader)):
        #data = data.view(data.size(0), -1)
        X, Y = X.to(device=device), Y.to(device=device)
        pred = target_model(X)
        #org_data=data
        #data= data.view(-1,32*32*3)
        '''
        target_outputs = target_model.first_part(data)
        target_outputs = target_outputs.view(1, 32, target_outputs.shape[0], 16*16)
        #target_outputs= target_outputs.view(-1,32*32*500)
        #target_outputs = target_model.second_part(target_outputs)
        #target_outputs = target_model(data)
        recreated_data = attack_model(target_outputs)
        recreated_data=torch.permute(recreated_data, (2,1, 0,3))
        recreated_data=recreated_data.repeat(1,1,32,1) 
        print(data.shape)
        #print(data.shape)
        #print(target_outputs.shape)
        print(recreated_data.shape)
        #data=data.resize(64, 3, 32, 32)
        #recreated_data=recreated_data.resize(64, 3, 32, 32)
        #print(recreated_data.shape)
        '''
        #for i in range(Y[0]):
        label=Y
        recreated_data=generate_img(generator, label)
        #print(recreated_data.shape)
        
        #print(recon_img.shape)
        recon_img=recreated_data
        recon_img=recon_img.to(device=device)
        pred2 = target_model(recon_img)
        recon_img=recon_img.unsqueeze(0).repeat(1, 1, 1, 1)
        recreated_data=recon_img
        
        #batch_count+=batch
        #correct += (pred.argmax(1)==Y).type(torch.float).sum().item()
      
        psnr = PeakSignalNoiseRatio().to(device)
        psnr_val=abs(psnr(X, recreated_data).item())
        print("PSNR is:", psnr_val)
        
        ssim = StructuralSimilarityIndexMeasure(data_range=1.0).to(device)
        ssim_val=abs(ssim(X, recreated_data).item()*10.00)
        print("SSIM is:", ssim_val)

        ## Inception Score

        data_scaled=torch.mul(torch.div(torch.sub(X, torch.min(X)),torch.sub(torch.max(X),torch.min(X))), 255)
        int_data=data_scaled.to(torch.uint8)
        recon_scaled=torch.mul(torch.div(torch.sub(recreated_data, torch.min(recreated_data)),torch.sub(torch.max(recreated_data),torch.min(recreated_data))), 255)
        int_recon=recon_scaled.to(torch.uint8)
        #print(int_data, int_recon)
        fid_val = abs(calculate_fid(int_data[0][0].cpu().detach().numpy(), int_recon[0][0].cpu().detach().numpy()))
        if (fid_val=='nan'):
           fid_val=Average(fid_lst)
        print('FID is: %.3f' % fid_val)
        #gen_data= recreated_data.view(-1,32*32*3)

        #test_output = target_model(recreated_data)
        #attack_pred = test_output.max(1, keepdim=True)[1] # get the index of the max log-probability
        #print(f"Done with sample: {counter_a}\ton epsilon={epsilon}")

        #if attack_pred.item() == targets.item():
        #    attack_correct += 1        
        _, pred = torch.max(pred2, -1)
        attack_correct += (pred == Y).sum().item()
        total += Y.size(0)
        '''
        DataI = data[0] / 2 + 0.5
        img= torch.permute(DataI, (1,2, 0))
        #img=img.to(torch.float32)
        #print(img.shape)
        plt.imshow((img.cpu().detach().numpy()))
        plt.xticks([])
        plt.yticks([])
        
        #plt.imshow(mfcc_spectrogram[0][0,:,:].numpy(), cmap='viridis')
        DataR=recreated_data[0]/2 + 0.5
        recon_img=torch.permute(DataR, (1,2, 0))
        #print(recon_img.shape)
        plt.draw()
        plt.savefig(f'./etn_plot/CIFAR/gan/org_img{batch}.jpg', dpi=100, bbox_inches='tight')
        plt.imshow((recon_img.cpu().detach().numpy()))
        plt.xticks([])
        plt.yticks([])
        #plt.imshow(mfcc_spectrogram[0][0,:,:].numpy(), cmap='viridis')
        plt.draw()
        plt.savefig(f'./etn_plot/CIFAR/gan/recon_img{batch}.jpg', dpi=100, bbox_inches='tight')
        '''
        psnr_lst.append(psnr_val)
        ssim_lst.append(ssim_val)
        fid_lst.append(fid_val)
    
    attack_acc = attack_correct/float(total)
    print(f" Attack Performance = {attack_correct} / {total} = {attack_acc}\t")

    return psnr_lst, ssim_lst, fid_lst

target_epochs=25
loss_train_tr, loss_test_tr=[],[]
for t in tqdm(range(target_epochs)):
    print(f'Epoch {t+1}\n-------------------------------')
    print("+++++++++Target Training Starting+++++++++")
    tr_loss, result_train=target_train(train_loader, target_model, optimiser)
    loss_train_tr.append(tr_loss)

print("+++++++++Target Test+++++++++")

final_acc=target_utility(test_loader, target_model, batch_size=1)
attack_epochs=50

loss_train, loss_test=[],[]
for t in tqdm(range(attack_epochs)):
    print(f'Epoch {t+1}\n-------------------------------')
    print("+++++++++Training Starting+++++++++")
    tr_loss=attack_train(test_loader, target_model, attack_model, optimiser)
    loss_train.append(tr_loss)

print("**********Test Starting************")
psnr_lst, ssim_lst, fid_lst=attack_test(attack_test_loader, target_model, attack_model)


print('Done!')



average_psnr = Average(psnr_lst)
average_ssim = Average(ssim_lst)
average_incep = Average(fid_lst)
print('Mean scoers are>> PSNR, SSIM, FID: ', average_psnr, average_ssim, average_incep)

#torch.save(attack_model, '/vast/home/sdibbo/def_ddlc/model_attack/etn/gan_CIFAR10_20_epoch_CNN_linear_attack.pt')
#torch.save(target_model, '/vast/home/sdibbo/def_ddlc/model_target/etn/gan_CIFAR10_20_epoch_CNN_linear_target.pt')

df = pd.DataFrame(list(zip(*[psnr_lst,  ssim_lst, fid_lst]))).add_prefix('Col')

print("--- %s seconds ---" % (time.time() - start_time))

#torch.save(attack_model, '/vast/home/sdibbo/def_ddlc/model_attack/etn/gan_MNIST_20_epoch_CNN_linear_attack.pt')
#torch.save(target_model, '/vast/home/sdibbo/def_ddlc/model_target/etn/gan_MNIST_20_epoch_CNN_linear_target.pt')

#df = pd.DataFrame(list(zip(*[psnr_lst,  ssim_lst, fid_lst]))).add_prefix('Col')

#df.to_csv('/vast/home/sdibbo/def_ddlc/result/etn/gan_MNIST_20_epoch_CNN_attack_linear.csv', index=False)
