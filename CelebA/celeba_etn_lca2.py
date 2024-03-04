import os
import zipfile 
import gdown
import torch
import torchvision
from natsort import natsorted
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms
from skimage import io
from tqdm import tqdm
import numpy as np
import pandas as pd
from torch import nn, optim
from torchmetrics.image import PeakSignalNoiseRatio, StructuralSimilarityIndexMeasure
from torchmetrics.image.fid import FrechetInceptionDistance
from torchmetrics.image.lpip import LearnedPerceptualImagePatchSimilarity
from torchmetrics.image.inception import InceptionScore
import matplotlib.pyplot as plt
import pandas as pd
from collections import Counter
import numpy as np
import torch.nn.functional as F
from numpy import iscomplexobj
from numpy import cov
from numpy import trace
from scipy.linalg import sqrtm
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as transforms
from skimage import io
from lcapt.lca import LCAConv2D

## Setup
# Number of gpus available
ngpu = 1
device = torch.device('cuda:0' if (
    torch.cuda.is_available() and ngpu > 0) else 'cpu')
batch_size = 32
batch_size_train = 8
batch_size_test = 16
num_workers=0

## Fetch data from Google Drive 
# Root directory for the dataset
data_root = '/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/data'
# Path to folder with the dataset
dataset_folder = f'{data_root}/img_align_celeba/img_align_celeba'


class FaceCelebADataset(Dataset):
    """Face Landmarks dataset."""

    def __init__(self, csv_file, root_dir, transform=None):
        """
        Arguments:
            csv_file (string): Path to the csv file with annotations.
            root_dir (string): Directory with all the images.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        self.landmarks_frame = pd.read_csv(csv_file)
        self.root_dir = root_dir
        self.transform = transform

    def __len__(self):
        return len(self.landmarks_frame)

    def __getitem__(self, idx):
        if torch.is_tensor(idx):
            idx = idx.tolist()

        img_name = os.path.join(self.root_dir,
                                self.landmarks_frame.iloc[idx, 0])
        image = io.imread(img_name)
        landmarks_bald = self.landmarks_frame.iloc[idx, 5]
        landmarks_black = self.landmarks_frame.iloc[idx, 9]
        landmarks_blond = self.landmarks_frame.iloc[idx, 10]
        landmarks_brown = self.landmarks_frame.iloc[idx, 12]
        landmarks_gray = self.landmarks_frame.iloc[idx, 18]
            
        landmarks=abs(landmarks_bald+landmarks_black+ landmarks_blond + landmarks_brown+ landmarks_gray)
        #landmarks = self.landmarks_frame.iloc[idx, 1]
        y_label = torch.tensor(int(landmarks))
        #landmarks = np.array([landmarks], dtype=float).reshape(-1, 2)
        sample = {'image': image, 'landmarks': y_label}
        

        if self.transform:
            image = self.transform(image)
        
        return (image, y_label)
        

transform__op=torchvision.transforms.Compose([
                                 #transforms.ToPILImage(),

                               torchvision.transforms.ToTensor(),
                                                         torchvision.transforms.Resize((32)),
                                                          transforms.CenterCrop(32),
                                                         transforms.Normalize(mean=[0.5, 0.5, 0.5],
                          std=[0.5, 0.5, 0.5])
                              ])

face_dataset = FaceCelebADataset(csv_file='/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/data/list_attr_celeba.csv',
                                    root_dir=dataset_folder, transform=transform__op)
#face_dataset = FaceLandmarksDataset(csv_file='/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/data/list_landmarks_align_celeba.csv',
#                                    root_dir=dataset_folder, transform=transform__op)
print(len(face_dataset))
train_set, test_set_org = torch.utils.data.random_split(face_dataset,
                                                   [50000,152599])
test_set, test_set2 = torch.utils.data.random_split(test_set_org,
                                                   [20000,132599])
train_loader = DataLoader(train_set,   batch_size=batch_size_train, shuffle=True)
test_loader = DataLoader(test_set, batch_size=batch_size_test, shuffle=True)

  
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # use gpu if available
#152624
'''
## Create a custom Dataset class
class CelebADataset(Dataset):
  def __init__(self, root_dir, transform=None):
    """
    Args:
      root_dir (string): Directory with all the images
      transform (callable, optional): transform to be applied to each image sample
    """
    # Read names of images in the root directory
    image_names = os.listdir(root_dir)

    self.root_dir = root_dir
    self.transform = transform 
    self.image_names = natsorted(image_names)

    def __len__(self): 
        #len(self.annotations)
        return len(self.image_names)

    def __getitem__(self, idx):
        # Get the path to the image 
        img_path = os.path.join(self.root_dir, self.image_names[idx])
        # Load image and convert it to RGB
        img = Image.open(img_path).convert('RGB')
        # Apply transformations to the image
        if self.transform:
            img = self.transform(img)

        return img
    ## Load the dataset 
# Path to directory with all the images
img_folder = f'{dataset_folder}/img_align_celeba'
# Spatial size of training images, images are resized to this size.
image_size = 32
# Transformations to be applied to each individual image sample
transform=transforms.Compose([
    transforms.Resize(image_size),
    transforms.CenterCrop(image_size),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5, 0.5, 0.5],
                          std=[0.5, 0.5, 0.5])
])
# Load the dataset from file and apply transformations
celeba_dataset = CelebADataset(img_folder, transform)
print(celeba_dataset)
## Create a dataloader 
# Batch size during training
batch_size = 128
# Number of workers for the dataloader
num_workers = 0 if device.type == 'cuda' else 2
# Whether to put fetched data tensors to pinned memory

pin_memory = True if device.type == 'cuda' else False

celeba_dataloader = torch.utils.data.DataLoader(celeba_dataset,
                                                batch_size=batch_size,
                                                num_workers=num_workers,
                                                pin_memory=pin_memory,
                                                )
                                                '''

print("Working Fine")
size1 = len(train_loader)
size2 = len(test_loader)

print(size1, size2)

class SplitNN(nn.Module):
  def __init__(self):
    super(SplitNN, self).__init__()
    self.first_part = nn.Sequential(
     LCAConv2D(out_neurons=16,
                in_neurons=3,                        
                kernel_size=5,              
                stride=1,                   
                 lambda_=1.5, lca_iters=500, pad="same",               
            ),                               
            nn.ReLU(), 
            nn.Dropout(.09), 
            #nn.MaxPool2d(2, 2), 
            nn.BatchNorm2d(16) ,                   
    LCAConv2D(out_neurons=32,
                in_neurons=16,                        
                kernel_size=5,              
                stride=1,                   
                 lambda_=1.5, lca_iters=500, pad="same", ),    
                                         nn.ReLU(), 
            nn.Dropout(.09), 
            nn.MaxPool2d(2, 2),
            nn.BatchNorm2d(32),                    

                         )
    self.second_part = nn.Sequential(
                           nn.Conv2d(32, 64, 5, 1, 2),     
                            nn.ReLU(), 
                            nn.Dropout(.09), 
                            nn.MaxPool2d(2, 2),
                            nn.BatchNorm2d(64),   
                            nn.Conv2d(64, 128, 5, 1, 2),     
                            nn.ReLU(), 
                            nn.Dropout(.09), 
                            nn.MaxPool2d(2, 2),
                            nn.BatchNorm2d(128), 
                            nn.Conv2d(128, 256, 5, 1, 2),     
                            nn.ReLU(), 
                            nn.Dropout(.09),  
                            nn.MaxPool2d(2, 2),
                            nn.BatchNorm2d(256),  
                            
                           #scancel nn.Softmax(dim=-1),
                         )
    self.third_part = nn.Sequential(
                            nn.Linear(256*2*2, 500),
                            nn.ReLU(),
                            nn.Linear(500, 5),
       

    )

  def forward(self, x):
    x=self.first_part(x)
    #print(x.shape)
    #x = torch.flatten(x, 1) # flatten all dimensions except batch
    #x = x.view(-1, 32*16*500)
    #print(x.shape)
    x=self.second_part(x)
    #print(x.shape)
    x = x.view(-1, 256*2*2)
    x=self.third_part(x)
    #print(x.shape)

    return x



target_model = SplitNN().to(device=device, dtype=torch.float16)
class Attacker(nn.Module):
  def __init__(self):
    super(Attacker, self).__init__()
    self.layers= nn.Sequential(
                     nn.Linear(256, 512),
                      nn.ReLU(),
                      nn.Linear(512, 32),
                      nn.ReLU(),
                      nn.ConvTranspose2d(32, 16, 5, 1, 2, bias=False),
                      nn.BatchNorm2d(16),
                      nn.ReLU(),
                      nn.ConvTranspose2d(16, 10, 5, 1, 2, bias=False),
                      nn.BatchNorm2d(10),
                      nn.ReLU(),
                      nn.ConvTranspose2d(10, 3, 5, 1, 2, bias=False),

                    )
 
  def forward(self, x):
    return self.layers(x)
  
attack_model = Attacker().to(device=device, dtype=torch.float16)
optimiser=torch.optim.SGD(target_model.parameters(),lr=0.001,momentum=0.9)
cost = torch.nn.CrossEntropyLoss()

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
 return fid


def target_train(train_loader, target_model, optimiser):
    target_model.train()
    size = len(train_loader.dataset)
    correct = 0
    total_loss=[]
    for batch, (X, Y) in enumerate(tqdm(train_loader)):
        Y=Y-1
        X, Y = X.to(device=device, dtype=torch.float16), Y.to(device=device)
        #print(X, Y)
        target_model.zero_grad()
        pred = target_model(X)
        #print(pred.shape, Y.shape)
        loss = cost(pred, Y)
        loss.backward()
        optimiser.step()
        _, output = torch.max(pred, 1)
        correct+= (output == Y).sum().item()
        total_loss.append(loss.item())
        #batch_count+=batch
        #correct += (pred.argmax(1)==Y).type(torch.float).sum().item()

    correct /= size
    loss= sum(total_loss)/batch
    result_train=100*correct
    print(f'\nTraining Performance:\nacc: {(100*correct):>0.1f}%, avg loss: {loss:>8f}\n')
    
    return loss, result_train

#test_loader, target_model, attack_model, optimiser
def attack_train(test_loader, target_model, attack_model, optimiser):
#for data, targets in enumerate(tqdm(train_loader)):
    for batch, (data, targets) in enumerate(tqdm(test_loader)):
    # Reset gradients
        data, targets = data.to(device=device, dtype=torch.float16), targets.to(device=device)
        optimiser.zero_grad()
        #index, data = data   
        #print(data.shape)
        #data=data.view(1000, 784)
        #data=torch.transpose(data, 0, 1)
        # First, get outputs from the target model
        target_outputs = target_model.first_part(data)
        target_outputs = target_model.second_part(target_outputs)
        #print(data.shape)
        #print(target_outputs.shape)
        target_outputs = target_outputs.view(1, 2*data.shape[0], 2, 16*16)
        #print(target_outputs.shape)
        # Next, recreate the data with the attacker
        #target_outputs=target_outputs[None, None, :]
        attack_outputs = attack_model(target_outputs)
        #print(attack_outputs.shape)
        #print(attack_outputs.shape)
        attack_outputs = attack_outputs.repeat(data.shape[0], 1, data.shape[0], 1)
        #print(attack_outputs.shape)
        '''
        #print(data.shape)
        data= torch.mean(data, -1)
        data=torch.permute(data, (1,0, 2))
        data = data[None,:, :,  :]
        '''
        #print(data.shape)
        #print(target_outputs.shape)
       # print(attack_outputs.shape)
        #attack_outputs= torch.permute(attack_outputs, (0,3,1,2))

        # We want attack outputs to resemble the original data
        loss = ((data - attack_outputs)**2).mean()

        # Update the attack model
        loss.backward()
        optimiser.step()

    return loss

def target_utility(test_loader, target_model, batch_size=1):
    size = len(test_loader.dataset)
    #target_model.eval()
    test_loss, correct = 0, 0
    correct = 0
    total=0
    counter_a=0
    #with torch.no_grad():
    for batch, (X, Y) in enumerate(tqdm(test_loader)):
        X, Y = X.to(device=device, dtype=torch.float16), Y.to(device=device)
        X.requires_grad = True
        pred = target_model(X)
        counter_a=counter_a+1
        #test_loss += cost(pred, Y).item()
        #correct += (pred.argmax(1)==Y).type(torch.float).sum().item()


        #data, target = data.to(device), target.to(device)
       
        # Set requires_grad attribute of tensor. Important for Attack
        total += Y.size(0)
        # Forward pass the data through the model
        _, output_res = torch.max(pred, -1)
        correct += ((output_res+1) == Y).sum().item()


    # Calculate final accuracy for this epsilon
    final_acc = correct/float(total)
    print(f"Target Model Accuracy = {correct} / {total} = {final_acc}")

    # Return the accuracy and an adversarial example
    return final_acc 


def attack_test(train_loader, target_model, attack_model):
    psnr_lst, ssim_lst, fid_lst=[], [], []
    attack_correct=0
    total=0
    for batch, (data, targets) in enumerate(tqdm(train_loader)):
        #data = data.view(data.size(0), -1)
        data, targets = data.to(device=device, dtype=torch.float16), targets.to(device=device)
        target_outputs = target_model.first_part(data)
        target_outputs = target_model.second_part(target_outputs)
        if (data.shape[0]!=32):
           #data=data.repeat(2, 1, 1, 1)
           target_outputs = target_outputs.view(1,data.shape[0], 4, 16*16)
           target_outputs = target_outputs.repeat(1,2, 1, 1)
        else:
            target_outputs = target_outputs.view(1,data.shape[0], 4, 16*16)
        #print(data.shape)
        #print(target_outputs.shape)
        print(target_outputs.shape)
        #target_outputs = target_outputs.view(1, 32, target_outputs.shape[0], 16*16)
        #target_outputs=target_outputs[None, None, :]
        if(target_outputs.shape[1]!=32):
            target_outputs = target_outputs.repeat(1,2, 1, 1)
        recreated_data = attack_model(target_outputs)
        #print(recreated_data.shape)
        recreated_data = recreated_data.repeat(data.shape[0], 1,8, 1)
        #recreated_data= torch.permute(recreated_data, (0,3,1,2))
        #print(recreated_data.shape)
        '''
        data= torch.mean(data, -1)
        data=torch.permute(data, (1,0, 2))
        data = data[None,:, :,  :]
        '''
        psnr = PeakSignalNoiseRatio().to(device)
        psnr_val=abs(psnr(data, recreated_data).item())
        if (psnr_val=='-inf'):
           psnr_val=Average(psnr_lst)
        print("PSNR is:", psnr_val)
        #print("PSNR is:", psnr_val)
        
        ssim = StructuralSimilarityIndexMeasure(data_range=1.0).to(device)
        ssim_val=abs(ssim(data, recreated_data).item())
        print("SSIM is:", ssim_val)

        #LEARNED PERCEPTUAL IMAGE PATCH SIMILARITY (LPIPS)
        #lpips = LearnedPerceptualImagePatchSimilarity(net_type='squeeze')
        #lpips_val=lpips(data, recreated_data).item()
        #print("LPIPS is:", lpips_val)

        '''
        fid = FrechetInceptionDistance(feature=768)
        int_data=data.to(torch.uint8)
        int_recon=recreated_data.to(torch.uint8)
        fid.update(int_data, real=True)
        fid.update(int_recon, real=False)
        fid_val=fid.compute()
        print("FID is:", fid_val)
        '''
        ## Inception Score
        data_scaled=torch.mul(torch.div(torch.sub(data, torch.min(data)),torch.sub(torch.max(data),torch.min(data))), 255)
        int_data=data_scaled.to(torch.uint8)
        recon_scaled=torch.mul(torch.div(torch.sub(recreated_data, torch.min(recreated_data)),torch.sub(torch.max(recreated_data),torch.min(recreated_data))), 255)
        int_recon=recon_scaled.to(torch.uint8)
        fid_val = calculate_fid(int_data[0][0].cpu().detach().numpy(), int_recon[0][0].cpu().detach().numpy())
        if (fid_val=='nan'):
           fid_val=Average(fid_val)
        print("FID is:", fid_val)
        #print('FID is: %.3f' % fid_val)
        if (recreated_data.shape[2]==16):
           recreated_data=recreated_data.repeat(1, 1, 2, 1)
        test_output = target_model(recreated_data)
        #attack_pred = test_output.max(1, keepdim=True)[1] # get the index of the max log-probability
        #print(f"Done with sample: {counter_a}\ton epsilon={epsilon}")

        #if attack_pred.item() == targets.item():
        #    attack_correct += 1      
        #            plt.savefig(f'/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/plot/guard/org_img{batch}.jpg', dpi=100, bbox_inches='tight')  
        _, pred = torch.max(test_output, -1)
        attack_correct += (pred == targets).sum().item()
        total += targets.size(0)
        ### For Saving recon images, uncomment below code blocks
        '''
        if (psnr_val>15.00):
        ### For Saving recon images, uncomment below code blocks
        
            DataI = (data[0] / 2 + 0.5).to(torch.float32)
            img= torch.permute(DataI, (1,2, 0))
            #print(img.shape)
            plt.imshow((img.cpu().detach().numpy()))
            plt.xticks([])
            plt.yticks([])
            
            #plt.imshow(mfcc_spectrogram[0][0,:,:].numpy(), cmap='viridis')
            DataR=(recreated_data[0]/2 + 0.5).to(torch.float32)
            recon_img=torch.permute(DataR, (1,2, 0))
            #recon_img=torch.max(img, recon_img)
            recon_img=img-max(recon_img)[0].item()
            #print(recon_img.shape)
            plt.draw()
            plt.savefig(f'/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/plot/test/org_img{batch}.jpg', dpi=100, bbox_inches='tight')
            plt.imshow((recon_img.cpu().detach().numpy()))
            plt.xticks([])
            plt.yticks([])
            #plt.imshow(mfcc_spectrogram[0][0,:,:].numpy(), cmap='viridis')
            plt.draw()
            plt.savefig(f'/dartfs-hpc/rc/home/h/f0048vh/Sparse_guard/celeba/plot/test/recon_img{batch}.jpg', dpi=100, bbox_inches='tight')
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
psnr_lst, ssim_lst, fid_lst=attack_test(train_loader, target_model, attack_model)
def Average(lst):
    return sum(lst) / len(lst)

print('Done!')


average_psnr = Average(psnr_lst)
average_ssim = Average(ssim_lst)
average_incep = Average(fid_lst)
print('Mean scoers are>> PSNR, SSIM, FID: ', average_psnr, average_ssim, average_incep)

#torch.save(attack_model, '/vast/home/sdibbo/def_ddlc/model_attack/CIFAR10_20_epoch_CNN_cnn_attack.pt')
#torch.save(target_model, '/vast/home/sdibbo/def_ddlc/model_target/CIFAR10_20_epoch_CNN_cnn_target.pt')

df = pd.DataFrame(list(zip(*[psnr_lst,  ssim_lst, fid_lst]))).add_prefix('Col')

#df.to_csv('/vast/home/sdibbo/def_ddlc/result/CIFAR10_20_epoch_CNN_attack_cnn.csv', index=False)

