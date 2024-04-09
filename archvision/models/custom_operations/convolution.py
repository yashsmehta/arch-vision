from models.custom_operations.preset_filters import filters, generate_discrete_wavelet_family
from torch.nn import functional as F
import math
import torch
torch.manual_seed(42)
from torch import nn
import numpy as np

discrete_wavelets = ['bior', 'coif', 'db', 'dmey', 'haar', 'rbio', 'sym']
cont_wavelets = ['cmor' , 'shan' , 'fbsp' ,'cgau' ,'gaus' ,'mexh' ,'morl']


class WaveletConvolution(nn.Module):
    
    
    def __init__(self, 
                 filter_type:str,
                 filter_params:dict=None,
                 filter_size:int=None,
                 device:str=None

                ):
                
        super().__init__()
        

        self.filter_type = filter_type
        self.filter_size = filter_size
        self.filter_params = get_kernel_params(self.filter_type)
        self.layer_size = get_layer_size(self.filter_type, self.filter_params)
        self.device = device
    
    def extra_repr(self) -> str:
        return 'filter_size={filter_size}, filter_params:{filter_params}'.format(**self.__dict__)
    
    
    def forward(self,x):
            
        x = x.to(self.device)
        
        in_channels = x.shape[1]
        
        convolved_tensor = []
        
        if self.filter_type in ['curvature','gabor']:
            weights = filters(in_channels=1, kernel_size=self.filter_size, filter_type = self.filter_type, filter_params=self.filter_params).to(self.device)
            for i in range(in_channels):
                    channel_image = x[:, i:i+1, :, :]
                    channel_convolved = F.conv2d(channel_image, weight= weights.to(self.device), padding=weights.shape[-1] // 2 - 1)
                    convolved_tensor.append(channel_convolved)
                    
        elif self.filter_type in discrete_wavelets:
            weights= generate_discrete_wavelet_family(wavelet_family=self.filter_type)
            print('test')
            for weights in weights:
                for i in range(in_channels):
                    channel_image = x[:, i:i+1, :, :]
                    channel_convolved = F.conv2d(channel_image, weight= weights.to(self.device), padding=weights.shape[-1] // 2 - 1)
                    convolved_tensor.append(channel_convolved)

        elif self.filter_type in cont_wavelets:
            weights= generate_continuous_wavelet_filters(wavelet_family=self.filter_type, num_scales=3)
            
            for weights in weights:
                for i in range(in_channels):
                    channel_image = x[:, i:i+1, :, :]
                    channel_convolved = F.conv2d(channel_image, weight= weights.to(self.device), padding=weights.shape[-1] // 2 - 1)
                    convolved_tensor.append(channel_convolved)
            
            
        
        # for RGB input (the preset L1 filters are repeated across the 3 channels)
        
        x = torch.cat(convolved_tensor, dim=1)   
 
        return x    



        
def initialize_conv_layer(conv_layer, initialization):
    
    init_type = ['kaiming_uniform', 'kaiming_normal', 'orthogonal', 'xavier_uniform', 'xavier_normal', 'uniform','normal']

    assert initialization in init_type, f'invalid initialization type, choose one of {init_type}'
        
    match initialization:
        
        case 'kaiming_uniform':
            torch.nn.init.kaiming_uniform_(conv_layer.weight)
            
        case 'kaiming_normal':
            torch.nn.init.kaiming_normal_(conv_layer.weight)
            
        case 'orthogonal':
            torch.nn.init.orthogonal_(conv_layer.weight) 
            
        case 'xavier_uniform':
            torch.nn.init.xavier_uniform_(conv_layer.weight) 
            
        case 'xavier_normal':
            torch.nn.init.xavier_normal_(conv_layer.weight)  
            
        case 'uniform':
            torch.nn.init.uniform_(conv_layer.weight)     
            
        case 'normal':
            torch.nn.init.normal_(conv_layer.weight)     

    return

        
        


def change_weights(module, SVD=False):
    
    if SVD:  
        device = torch.device('cuda')  # Using GPU

        n_channels = module.weight.shape[0]  # =n_filters (out)
        n_elements = module.weight.shape[1] * module.weight.shape[2] * module.weight.shape[3]  # =in_channels*kernel_height*kernel_width
        n_components = min(n_channels, n_elements)
        power_law_exponent = -1  # Exponent of power law decay

        # Create decomposed matrices
        U, _ = torch.linalg.qr(torch.randn(n_channels, n_components, device=device))
        V, _ = torch.linalg.qr(torch.randn(n_elements, n_components, device=device))
        V_T = V.T

        eigenvalues = torch.pow(torch.arange(1, n_components + 1, dtype=torch.float32, device=device), power_law_exponent)
        S = torch.zeros((n_components, n_components), device=device)
        
        # Correct way to fill the diagonal
        torch.diagonal(S).copy_(torch.sqrt(eigenvalues * (n_channels - 1)))

        # Calculate data with specified eigenvalues
        X = U @ S @ V_T

        # Reshape and set weights
        weights = X.reshape(n_channels, module.weight.shape[1], module.weight.shape[2], module.weight.shape[3])
        module.weight = torch.nn.Parameter(data=weights)
        return module
        
        
    else:
        
        in_size = module.weight.shape[1]
        k_size = module.weight.shape[2]
        n_channels = module.weight.shape[0]

        n_elements = in_size * k_size * k_size
        power_law_exponent = -1

        # Efficient computation of eigenvalues
        eigenvalues = np.arange(1, n_elements + 1, dtype=np.float32) ** power_law_exponent

        # Direct generation of an orthonormal matrix
        eigenvectors = torch.linalg.qr(torch.randn(n_elements, n_elements))[0]

        # Scale eigenvectors' variances
        eigenvectors = eigenvectors * torch.sqrt(torch.from_numpy(eigenvalues))[None, :]

        # Generate random data and compute weights
        X = torch.randn(n_channels, n_elements) @ eigenvectors
        weights = X.reshape(n_channels, in_size, k_size, k_size)

        # Update module weights
        module.weight = torch.nn.Parameter(weights)
        return module



def get_kernel_params(kernel_type):
    
    if kernel_type == 'curvature':
        return {'n_ories':12,'n_curves':3,'gau_sizes':(5,),'spatial_fre':[1.2]}
    
    elif kernel_type == 'gabor':
         return {'n_ories':12,'num_scales':3}
        
    elif kernel_type in discrete_wavelets:
        return None

    else:
        raise ValueError(f"Unsupported kernel type: {kernel_type}")



def get_layer_size(kernel_type, kernel_params):


        if kernel_type == 'curvature':
            return kernel_params['n_ories']*kernel_params['n_curves']*len(kernel_params['gau_sizes']*len(kernel_params['spatial_fre']))*3
        
        elif kernel_type == 'gabor':
            return kernel_params['n_ories']*kernel_params['num_scales']*3
       
        elif kernel_type in discrete_wavelets:
            wavelet_list = [i for i in pywt.wavelist() if kernel_type in i] 
            return len(wavelet_list) * 2 * 3
        
        else:
            raise ValueError(f"Unsupported kernel type: {kernel_type}")