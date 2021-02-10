import numpy as np
import sympy as sp
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def compute_pointset(output_file):
    # Define SDP variables
    x2, xy, y2, x, y, s2 = sp.symbols('x2, xy, y2, x, y, s2')
    # Goal pose
    g = np.array([1., 1.])
    # Form into a symmetric matrix
    Z = np.array([[x2, xy, x],
                  [xy, y2, y],
                  [x, y, s2]])
    Z = sp.Matrix(Z)

    # SDP cone boundary's equation (equals zero)
    sdp_boundary = sp.det(Z)

    # Linear constraints
    lin_constraints = [sp.Equality(s2, 1), sp.Equality(x2 + y2, 1), sp.Equality(x2 - 2*(x + y) + y2, -1)]
    constraints = lin_constraints + [sp.Equality(sdp_boundary, 0)]

    # Unit circle obstacle at [1, 0]
    obstacle_constraint_expression = x2 - 2*x + y2
    obstacle_constraint_converted = sp.GreaterThan(y, 0.5)  # Use this manually in the plotting, later: cuts out solution at the origin

    # Solve the system
    # solution = sp.solve_poly_system(lin_constraints + [sp.det(Z)], x2, xy, y2, x, y, s2)

    # Substitute in the linear constraints to reduce variables
    boundary_curve = sdp_boundary.subs(s2, 1)
    boundary_curve = boundary_curve.subs(x2, 1-y2)
    boundary_curve = boundary_curve.subs(x, 1-y)  # Reduce the second linear constraint with the first to get this
    boundary_curve = boundary_curve.simplify()

    # Plot the boundary
    n = 50
    xy_domain = np.linspace(0., 1., n)
    y_domain = xy_domain
    y2_domain = np.linspace(0., 1., n)

    eig1 = []
    eig2 = []
    eig3 = []
    full_points = []
    for xy_val in xy_domain:
        for y_val in y_domain:
            for y2_val in y2_domain:
                Z_val = np.array([[1.-y2_val, xy_val, 1. - y_val],
                                  [xy_val, y2_val, y_val],
                                  [1. - y_val, y_val, 1.]])
                eig_vals = np.linalg.eigvalsh(Z_val)
                eig1.append(eig_vals[0])
                eig2.append(eig_vals[1])
                eig3.append(eig_vals[2])
                full_points.append(np.array([xy_val, y_val, y2_val]))
    rank_tol = 1e-2
    rank_approx = [np.sum([eig1[idx] > rank_tol, eig2[idx] > rank_tol, eig3[idx] > rank_tol]) for idx in range(len(eig1))]

    psd_set = [idx for idx in range(len(eig1)) if eig1[idx] >= 0. and eig2[idx] >= 0. and eig3[idx] >= 0.]
    psd_set_x = [full_points[idx][0] for idx in psd_set]
    psd_set_y = [full_points[idx][1] for idx in psd_set]
    psd_set_z = [full_points[idx][2] for idx in psd_set]
    
    psd_points = np.array([np.array(psd_set_x), np.array(psd_set_y), np.array(psd_set_z)]).transpose()




    rank1_set_x = [full_points[idx][0] for idx in range(len(eig1)) if rank_approx[idx] == 1 and idx in psd_set]
    rank1_set_y = [full_points[idx][1] for idx in range(len(eig1)) if rank_approx[idx] == 1 and idx in psd_set]
    rank1_set_z = [full_points[idx][2] for idx in range(len(eig1)) if rank_approx[idx] == 1 and idx in psd_set]

    rank1_points = np.array([np.array(rank1_set_x), np.array(rank1_set_y), np.array(rank1_set_z)]).transpose() #Nx3

    rank2_set_x = [full_points[idx][0] for idx in range(len(eig1)) if rank_approx[idx] == 2 and idx in psd_set]
    rank2_set_y = [full_points[idx][1] for idx in range(len(eig1)) if rank_approx[idx] == 2 and idx in psd_set]
    rank2_set_z = [full_points[idx][2] for idx in range(len(eig1)) if rank_approx[idx] == 2 and idx in psd_set]

    rank2_points = np.array([np.array(rank2_set_x), np.array(rank2_set_y), np.array(rank2_set_z)]).transpose() #Nx3

    #Cache data
    data_dict = {'psd_points':psd_points, 'rank1_points': rank1_points, 'rank2_points': rank2_points}
    print('Saving data to ... {}'.format(output_file))
    np.save(output_file, data_dict, allow_pickle=True)
    print('...done.')

def plot_sdp_fig(data):
    rank1_points = data.item().get('rank1_points')
    rank2_points = data.item().get('rank2_points')

    fig = plt.figure()
    ax = fig.gca(projection='3d')
    # ax.scatter(psd_set_x, psd_set_y, psd_set_z, c='g', marker='.', s=10)
    ax.scatter(rank1_points[:,0], rank1_points[:,1], rank1_points[:,2], c='r', marker='o', s=20)
    #ax.scatter(rank2_points[:,0], rank2_points[:,1], rank2_points[:,2], c='b', marker='.', s=10)
    #plt.xlabel('$xy$')
    #plt.ylabel('$y$')
    ax.set_xlabel('$xY$')
    ax.set_ylabel('$y$')
    
    
    rank2_above_mask = rank2_points[:,2] > rank2_points[:,1]
    
    #Points of a Plane
    #(0,0,0), (0,1,1), (0.5,0.5,0.5)
    xx, yy = np.meshgrid(np.linspace(0,1,5), np.linspace(0,1,5))
    z = yy
    ax.plot_surface(xx, yy, z, alpha=0.25)

    ax.plot_trisurf(rank2_points[rank2_above_mask,0], \
        rank2_points[rank2_above_mask,1], \
        rank2_points[rank2_above_mask,2], cmap='summer', alpha=0.5, antialiased=True)

    ax.plot_trisurf(rank2_points[~rank2_above_mask,0], \
        rank2_points[~rank2_above_mask,1], \
        rank2_points[~rank2_above_mask,2], cmap='summer', alpha=0.5, antialiased=True)

    plt.grid()
    plt.show()


if __name__ == '__main__':
    cached_data_file = '/tmp/sdp_data_vis.npy'

    try:
        data = np.load(cached_data_file, allow_pickle=True)
        print('Using cached data file: {}'.format(cached_data_file))
    
    except IOError:
        print("Cached data not found. Generating...")
        compute_pointset(cached_data_file)
        data = np.load(cached_data_file, allow_pickle=True)
    
    plot_sdp_fig(data)


    # Surface

    # TODO: add obstacle, do heatmap, plot actual solutions, and use SDP constraint, NOT determinant!
    # TODO: to check the SDP constraint, simply construct the whole matrix and check its eigenvalues
    # TODO: have colours specifying the rank of the points on the boundary on the heatmap (simple function of eigs)
    # TODO: eventually, add convex iteration procedure, see how it does on this toy problem (nuclear norm prob. solves)
