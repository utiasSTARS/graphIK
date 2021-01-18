import numpy as np
import sympy as sp
import cvxpy as cp
import pandas as pd
import pickle
import matplotlib.pyplot as plt
import mosek
from graphik.utils.utils import list_to_variable_dict, constraint_violations, measure_perturbation
from graphik.solvers.constraints import constraints_from_graph, nearest_neighbour_cost, get_full_revolute_nearest_point
from graphik.solvers.sdp_formulations import SdpSolverParams
from graphik.solvers.solver_generic_sdp import SdpRelaxationSolver
from graphik.utils.roboturdf import load_ur10, load_truncated_ur10
from graphik.graphs.graph_base import RobotRevoluteGraph
from graphik.robots.robot_base import RobotRevolute
from graphik.utils.dgp import pos_from_graph

from progress.bar import ShadyBar as Bar
from matplotlib import rc
rc("font", **{"family": "serif", "serif": ["Computer Modern"], "size": 18})
rc("text", usetex=True)


if __name__ == '__main__':
    n = 2
    if n == 6:
        robot, graph = load_ur10()
    else:
        robot, graph = load_truncated_ur10(n)

    q = robot.random_configuration()

    #  This is used for the Macaulay2 outputs (which are not very useful, ran out of RAM for simple n=3 (4?) case)
    # full_input = np.zeros(n)
    # full_input = [0, np.pi/2, -np.pi/2, np.pi/2, np.pi/2, -np.pi/2]
    # input = full_input[:n]
    # q = list_to_variable_dict(input)

    G = graph.realization(q)
    P = pos_from_graph(G)
    ee_goals = {}
    for pair in graph.robot.end_effectors:
        for ee in pair:
            if 'p' in ee:
                ee_goals[ee] = graph.robot.get_pose(q, ee).trans
            else:
                for idx, key in enumerate(graph.node_ids):
                    if key == ee:
                        ee_goals[ee] = P[idx, :]

    # Form the big Jacobian (symbolically, perhaps?)
    constraints = constraints_from_graph(graph, ee_goals)
    vars = set()

    for cons in constraints:
        vars = vars.union(cons.free_symbols)

    N = len(vars)
    constraints_matrix = sp.Matrix([cons.args[0] - cons.args[1] for cons in constraints])
    J = constraints_matrix.jacobian(list(vars))

    # Substitute in the values at any feasible point to see if it is 'regular' (i.e., satisfies ACQ)
    subs_vals = {}

    for idx in range(1, N//6 + 1):
        p_idx = graph.robot.get_pose(q, f'p{idx}').trans
        subs_vals[sp.Symbol(f'p{idx}_x')] = p_idx[0]
        subs_vals[sp.Symbol(f'p{idx}_y')] = p_idx[1]
        subs_vals[sp.Symbol(f'p{idx}_z')] = p_idx[2]

    for idx, key in enumerate(graph.node_ids):
        if 'q' in key:
            subs_vals[sp.Symbol(key + '_x')] = P[idx, 0]
            subs_vals[sp.Symbol(key + '_y')] = P[idx, 1]
            subs_vals[sp.Symbol(key + '_z')] = P[idx, 2]

    J_subbed = J.subs(subs_vals)

    _, s, _ = np.linalg.svd(np.array(J_subbed).astype(float))
    rank_J_subbed = np.sum(np.abs(s) > 1e-6)  # 21

    #  We want ACQ to hold: rank_J_subbed = n - dim(variety)
    #                                  21 = 30 - dim(variety)
    #  So, the dim of our variety should be 9 - this is way too high, should be 1 (so J should be full rank)
    required_manifold_dim = len(vars) - rank_J_subbed

    #  Try Groebner basis analysis?
    # basis = sp.polys.groebner(constraints)

    #  TODO: can constraints that make the problem Archimedean be added? Hard because we don't have inequalities.
    #  Is the formulation already Archimmedean, though? Should check. Perhaps joint limits will be needed, but

    #  For Macaulay2
    # constraints_rational = [sp.nsimplify(cons) for cons in constraints]
    # constraints_m2 = [cons.args[0] - cons.args[1] for cons in constraints_rational]
    # m2_str = str(constraints_m2)
    # m2_str = m2_str.replace('**', '^')
    # m2_str = m2_str.replace('[', '').replace(']', '').replace('_', '')
    # print('R = QQ[' + str(list(vars)).replace('[', '').replace(']', '').replace('_', '') + ']')
    # print(f'I_dof{n} = ideal(' + m2_str + ')')
