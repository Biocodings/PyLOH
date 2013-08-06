'''
Created on 2013-07-31

@author: Yi Li
'''
import numpy as np

from pyloh import constants
from pyloh.preprocessing.io import Data
from pyloh.model.model_base import *
from pyloh.model.utils import *

class PoissonProbabilisticModel(ProbabilisticModel):
    def __init__(self):
        ProbabilisticModel.__init__(self)
        
    def preprocess_data(self):
        self.data.segments.compute_Lambda_S()
        
    def _init_components(self):
        self.trainer_class = PoissonModelTrainer
        
class PoissonModelTrainer(ModelTrainer):
    def __init__(self, priors, data, max_iters, stop_value):
        ModelTrainer.__init__(self, priors, data, max_iters, stop_value)
        
    def _init_components(self):
        self.latent_variables = PoissonLatentVariables(self.data)
        
        self.model_parameters = PoissonModelParameters(self.priors, self.data)
        
        self.log_likelihood = PoissonLogLikelihood(self.data)
    
    def _print_running_info(self, iters, log_likelihood, old_log_likelihood, ll_change):
        print "#" * 100
        print "# Running Info."
        print "#" * 100
        print "Number of iterations : ", iters
        print "New log-likelihood : ", log_likelihood
        print "Old log-likelihood : ", old_log_likelihood 
        print "Log-likelihood change : ", ll_change
    
        print "Parameters :"
        print "Tumor celluar frequency: {0}".format(self.model_parameters.parameters['phi']) 
        
class PoissonLatentVariables(LatentVariables):
    def __init__(self, data):
        LatentVariables.__init__(self, data)
    
    def update(self, parameters, iters):
        eta = constants.ETA
        burn_in = constants.BURN_IN
        
        if iters >= burn_in:
            eta = 1
        
        J = self.data.seg_num
        G = constants.GENOTYPES_TUMOR_NUM
        
        sufficient_statistics = {}
        
        sufficient_statistics['psi'] = np.zeros((J, G))
        sufficient_statistics['u'] = np.zeros((J, G))
        sufficient_statistics['v'] = np.zeros((J, G))
        sufficient_statistics['w'] = np.zeros((J, G))
        
        for j in range(0, J):
            psi_j, u_j, v_j, w_j = self._sufficient_statistics_by_segment(parameters, eta, j)
            sufficient_statistics['psi'][j, :] = psi_j
            sufficient_statistics['u'][j, :] = u_j
            sufficient_statistics['v'][j, :] = v_j
            sufficient_statistics['w'][j, :] = w_j
            
        self.sufficient_statistics = sufficient_statistics
    
    def _sufficient_statistics_by_segment(self, parameters, eta, j):
        G = constants.GENOTYPES_TUMOR_NUM
        
        a_T_j = self.data.paired_counts[j][:, 2]
        b_T_j = self.data.paired_counts[j][:, 3]
        d_T_j = a_T_j + b_T_j
        I_j = d_T_j.shape[0]
        D_N_j = self.data.segments[j][4]
        D_T_j = self.data.segments[j][5]
        rho_j = parameters['rho'][j]
        phi = parameters['phi']
        
        Lambda_S = self.data.segments.Lambda_S
        
        log_likelihoods_LOH = poisson_ll_func_LOH(b_T_j, d_T_j, rho_j, phi)
        log_likelihoods_CNV = poisson_ll_func_CNV(D_N_j, D_T_j, Lambda_S, rho_j, phi)

        xi_j = log_space_normalise_rows_annealing(log_likelihoods_LOH, eta)
        psi_j = log_space_normalise_rows_annealing(log_likelihoods_CNV, eta)
        
        u_j = np.add.reduce(xi_j, axis = 0)
        v_j = xi_j*np.dot(b_T_j.reshape(I_j, 1), np.ones((1, G)))
        v_j = np.add.reduce(v_j, axis = 0)
        w_j = xi_j*np.dot(d_T_j.reshape(I_j, 1), np.ones((1, G)))
        w_j = np.add.reduce(w_j, axis = 0)
        
        return psi_j, u_j, v_j, w_j

class PoissonModelParameters(ModelParameters):
    def __init__(self, priors, data):
        ModelParameters.__init__(self, priors, data)
    
    def update(self, sufficient_statistics):
        parameters = {}
                
        psi = sufficient_statistics['psi']
        u = sufficient_statistics['u']
        v = sufficient_statistics['v']
        w = sufficient_statistics['w']
        
        rho = self._update_rho(psi, u)
        phi = self._update_phi(v, w, rho)
        
        parameters['rho'] = rho
        parameters['phi'] = phi
        
        self.parameters = parameters
    
    def _update_rho(psi, u):
        x1 = constants.UPDATE_WEIGHTS['x1']
        y1 = constants.UPDATE_WEIGHTS['y1']
        z1 = constants.UPDATE_WEIGHTS['z1']
        
        I = np.array(self.data.sites_num)
        
        rho_CNV = psi
        
        rho_LOH = u/np.dot(I.reshape(J, 1), np.ones((1, G)))
        
        rho_priors = self._update_rho_by_priors()
        
        rho = x1*rho_CNV + y1*rho_LOH + z1*rho_priors
        
        return rho
    
    def _update_phi(self, v, w, rho):
        x2 = constants.UPDATE_WEIGHTS['x2']
        y2 = constants.UPDATE_WEIGHTS['y2']
        c_N = np.array(constants.COPY_NUMBER_NORMAL)
        c_T = np.array(constants.COPY_NUMBER_TUMOR)
        mu_N = np.array(constants.MU_N)
        mu_T = np.array(constants.MU_T)

        J = self.data.seg_num
        G = constants.GENOTYPES_TUMOR_NUM
        
        Lambda_S = self.data.segments.Lambda_S

        phi_CNV = np.zeros(J)
        phi_LOH = np.zeros(J)
        
        for j in range(0, J):
            D_N_j = self.data.segments[j][4]
            D_T_j = self.data.segments[j][5]
        
            c_E_j = D_T_j*c_N[0]/(D_N_j*Lambda_S)
            mu_E_j = v_j/w_j
            
            if c_E_j < min(c_T):
                c_E_j = min(c_T)
            elif e_E_j > max(c_T):
                c_E_j = max(c_T)
            
            for g in range(0, G):
                if mu_E_j[g] < min(mu_T):
                    mu_E_j[g] = min(mu_T)
                if mu_E_j[g] > max(mu_T):
                    mu_E_j[g] = max(mu_T)
            
            phi_CNV[j], phi_LOH[j] = self._update_phi_by_segment(c_E_j, mu_E_j, rho[j])
        
        phi = x2*phi_CNV.mean() + y2*phi_LOH.mean()
        
        return phi

    def _init_parameters(self):
        parameters = {}
        
        parameters['phi'] = constants.PHI_INIT
        parameters['rho'] = self._update_rho_by_priors()
        
        self.parameters = parameters
        
    def _update_rho_by_priors(self):
        J = self.data.seg_num
        G = constants.GENOTYPES_TUMOR_NUM
        
        omega = self.priors['omega']
        
        rho = np.zeros((J, G))
        
        for j in range(0, J):
            rho[j] = omega/omega.sum()
            
        return rho
    
    def _update_phi_by_segment(self, c_E_j, mu_E_j, rho_j):
        c_N = np.array(constants.COPY_NUMBER_NORMAL)
        c_T = np.array(constants.COPY_NUMBER_TUMOR)
        mu_N = np.array(constants.MU_N)
        mu_T = np.array(constants.MU_T)
        
        G = constants.GENOTYPES_TUMOR_NUM
        
        phi_CNV_j = 0
        phi_LOH_j = 0
        prob_sum_CNV = 0
        prob_sum_LOH = 0
         
        for g in range(0, G):
            phi_CNV_j_g = -1
            phi_LOH_j_g = -1
            
            if c_N[0] != c_T[g]:
                phi_CNV_j_g = get_phi(c_N[0], c_T[g], c_E_j)
            
            if mu_N[0] != mu_T[g]:
                phi_LOH_j_g = get_phi(mu_N[0], mu_T[g], mu_E_j[g])
                
            if phi_CNV_j_g >= 0 and phi_CNV_j_g <= 1:
                phi_CNV_j = phi_CNV_j + rho_j[g]*phi_CNV_j_g
                prob_sum_CNV = prob_sum_CNV + rho_j[g]
                
            if phi_LOH_j_g >= 0 and phi_LOH_j_g <= 1:
                phi_LOH_j = phi_LOH_j + rho_j[g]*phi_LOH_j_g
                prob_sum_LOH = prob_sum_LOH + rho_j[g]
                
        phi_CNV_j = phi_CNV_j/prob_sum_CNV
        phi_LOH_j = phi_LOH_j/prob_sum_LOH
        
        return (phi_CNV_j, phi_LOH_j)

#===============================================================================
# Function
#===============================================================================

def poisson_ll_func_LOH(b_T, d_T, rho, phi):
    I = d_T.shape[0]
    mu_N = np.array(constants.MU_N)
    mu_T = np.array(constants.MU_T)
    
    mu_E = get_x_E(mu_N, mu_T, phi)
        
    log_likelihoods = np.log(rho) + log_binomial_likelihood(b_T, d_T, mu_E)
    
    return log_likelihoods
    
def poisson_ll_func_CNV(D_N, D_T, Lambda_S, rho, phi):
    c_N = np.array(constants.COPY_NUMBER_NORMAL)
    c_T = np.array(constants.COPY_NUMBER_TUMOR)
    
    c_E = get_x_E(c_N, c_T, phi)
    
    lambda_E = D_N*c_E*Lambda_S/c_N
    
    log_likelihoods = np.log(rho) + log_poisson_likelihood(D_T, lambda_E)
    
    return log_likelihoods
    



