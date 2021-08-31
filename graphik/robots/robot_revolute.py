from typing import Any, Dict, Union, List
from numpy.typing import ArrayLike

import networkx as nx
import numpy as np
from graphik.robots.robot_base import Robot, SEMatrix
from graphik.utils import *

from liegroups.numpy import SE3
from numpy import arctan2, cos, cross, pi, sin

class RobotRevolute(Robot):
    def __init__(self, params):
        self.dim = 3
        self.n = params.get("num_joints", len(params["lb"]))  # number of joints
        self.axis_length = params.get("axis_length", 1)  # distance between p and q
        self.T_base = params.get("T_base", SE3.identity())  # base frame

        # Topological "map" of the robot, if not provided assume chain
        if "parents" in params:
            self.parents = nx.DiGraph(params["parents"])
        else:
            self.parents = nx.path_graph(
                [f"p{idx}" for idx in range(self.n + 1)], nx.DiGraph
            )

        # A dict of shortest paths between joints for forward kinematics
        self.kinematic_map = nx.shortest_path(self.parents)

        # Use frame poses at zero conf if provided, otherwise construct from DH
        if "T_zero" in params:
            self.T_zero = params["T_zero"]
        else:
            try:
                self.a, self.d, self.al, self.th, self.modified_dh = (
                    params["a"],
                    params["d"],
                    params["alpha"],
                    params["theta"],
                    params["modified_dh"],
                )
            except KeyError:
                raise Exception("Robot description not provided.")

        self.lb = params.get("lb", dict(zip(self.joint_ids, self.n * [-pi])))
        self.ub = params.get("ub", dict(zip(self.joint_ids, self.n * [pi])))

        super(RobotRevolute, self).__init__()

    def joint_variables(
        self, G: nx.DiGraph, T_final: Dict[str, SE3] = None
    ) -> Dict[str, Any]:
        print("joint_variables is not in RevoluteGraph")
        return {}


    @property
    def end_effectors(self) -> list:
        """
        Returns a list of end effector node pairs, since it's the
        last two points that are defined for a full pose.
        """
        if not hasattr(self, "_end_effectors"):
            self._end_effectors = [
                [x, f"q{x[1:]}"]
                for x in self.parents
                if self.parents.out_degree(x) == 0
            ]
        return self._end_effectors

    @property
    def S(self) -> dict:
        if not hasattr(self, "_S"):
            self._S = {}
            for joint, T in self.T_zero.items():
                omega = T.as_matrix()[:3,2]
                q = T.as_matrix()[:3,3]
                # self._S[joint] = SE3.wedge(np.hstack((np.cross(-omega, q), omega)))
                self._S[joint] = np.hstack((np.cross(-omega, q), omega))
        return self._S

    @S.setter
    def S(self, S: dict):
        self._S = S

    def get_pose(self, joint_angles: dict, query_node: str) -> SE3:
        kinematic_map = self.kinematic_map[ROOT][MAIN_PREFIX + query_node[1:]]
        T = self.T_base
        for idx in range(len(kinematic_map) - 1):
            pred, cur = kinematic_map[idx], kinematic_map[idx + 1]
            T = T.dot(SE3.exp(self.S[pred] * joint_angles[cur]))
        T = T.dot(self.T_zero[MAIN_PREFIX + query_node[1:]])

        if query_node[0] == AUX_PREFIX:
            T_trans = trans_axis(self.axis_length, "z")
            T = T.dot(T_trans)

        return T

    def jacobian(
        self,
        joint_angles: Dict[str, float],
        nodes: Union[List[str], str],
    ) -> Dict[str, ArrayLike]:
        """
        Calculate the robot's Jacobian for all end-effectors.

        :param joint_angles: dictionary describing the current joint configuration
        :param nodes: list of nodes that the Jacobian should be computed for
        :param Ts: the current list of frame poses for all nodes, speeds up computation
        :return: dictionary of Jacobians indexed by relevant node
        """
        kinematic_map = self.kinematic_map[ROOT]  # get map to all nodes from root

        # find end-effector nodes #FIXME so much code and relies on notation
        if nodes is None:
            nodes = []
            for ee in self.end_effectors:  # get p nodes in end-effectors
                if ee[0][0] == MAIN_PREFIX:
                    nodes += [ee[0]]
                elif ee[1][0] == MAIN_PREFIX:
                    nodes += [ee[1]]

        J = {}
        for node in nodes:  # iterate through nodes
            path = kinematic_map[node]  # find joints that move node
            T = self.T_base

            J[node] = np.zeros([6, self.n])
            for idx in range(len(path) - 1):
                pred, cur = path[idx], path[idx + 1]
                if idx == 0:
                    J[node][:, idx] = self.S[pred]
                else:
                    ppred = list(self.parents.predecessors(pred))[0]
                    T = T.dot(SE3.exp(self.S[ppred] * joint_angles[pred]))
                    Ad = T.adjoint()
                    J[node][:, idx] = Ad.dot(self.S[pred])
        return J

    @property
    def T_zero(self) -> dict:
        if not hasattr(self, "_T_zero"):
            T = {ROOT: self.T_base}
            kinematic_map = self.kinematic_map
            for ee in self.end_effectors:
                for node in kinematic_map[ROOT][ee[0]][1:]:
                    path_nodes = kinematic_map[ROOT][node][1:]

                    q = np.asarray([0 for node in path_nodes])
                    a = np.asarray([self.a[node] for node in path_nodes])
                    alpha = np.asarray([self.al[node] for node in path_nodes])
                    th = np.asarray([self.th[node] for node in path_nodes])
                    d = np.asarray([self.d[node] for node in path_nodes])

                    if not self.modified_dh:
                        T[node] = fk_3d(a, alpha, d, q + th)
                    else:
                        T[node] = modified_fk_3d(a, alpha, d, q + th)
            self._T_zero = T

        return self._T_zero

    @T_zero.setter
    def T_zero(self, T_zero: dict):
        self._T_zero = T_zero

    @property
    def parents(self) -> nx.DiGraph:
        return self._parents

    @parents.setter
    def parents(self, parents: nx.DiGraph):
        self._parents = parents

    def get_pose_old(self, joint_angles: dict, query_node: str) -> SE3:
        """
        Returns an SE3 element corresponding to the location
        of the query_node in the configuration determined by
        node_inputs.
        """
        kinematic_map = self.kinematic_map[ROOT][MAIN_PREFIX + query_node[1:]]

        T = self.T_base

        for idx in range(len(kinematic_map) - 1):
            pred, cur = kinematic_map[idx], kinematic_map[idx + 1]
            T_rel = self.structure[pred][cur][TRANSFORM]
            T_rot = rot_axis(joint_angles[cur], "z")
            T = T.dot(T_rot).dot(T_rel)

        if query_node[0] == "q":
            T_trans = trans_axis(self.axis_length, "z")
            T = T.dot(T_trans)

        return T

    def random_configuration(self):
        """
        Returns a random set of joint values within the joint limits
        determined by lb and ub.
        """
        q = {}
        for key in self.joint_ids:
            if key != ROOT:
                q[key] = self.lb[key] + (self.ub[key] - self.lb[key]) * np.random.rand()
        return q

    def zero_configuration(self):
        """
        Returns zero joint values within the joint limits
        determined by lb and ub.
        """
        q = {}
        for key in self.joint_ids:
            if key != ROOT:
                q[key] = 0
        return q

    def get_jacobian(
        self,
        joint_angles: Dict[str, float],
        nodes: Union[List[str], str],
        Ts: Dict[str, SEMatrix] = None,
    ) -> Dict[str, ArrayLike]:

        """
        Calculate the robot's linear velocity Jacobian for all end-effectors.

        :param joint_angles: dictionary describing the current joint configuration
        :param nodes: list of nodes that the Jacobian shoulf be computed for
        :param Ts: the current list of frame poses for all nodes, speeds up computation
        :return: dictionary of Jacobians indexed by relevant node
        """
        kinematic_map = self.kinematic_map[ROOT]  # get map to all nodes from root

        # find end-effector nodes #FIXME so much code and relies on notation
        if nodes is None:
            nodes = []
            for ee in self.end_effectors:  # get p nodes in end-effectors
                if ee[0][0] == MAIN_PREFIX:
                    nodes += [ee[0]]
                elif ee[1][0] == MAIN_PREFIX:
                    nodes += [ee[1]]

        if Ts is None:
            Ts = self.get_all_poses(joint_angles)  # compute all poses

        J = {}
        for node in nodes:  # iterate through nodes
            path = kinematic_map[node][1:]  # find joints that move node
            p_ee = Ts[node].trans

            J[node] = np.zeros([6, self.n])
            for idx, joint in enumerate(path):  # algorithm fills Jac per column
                T_0_i = Ts[list(self.parents.predecessors(joint))[0]]
                z_hat_i = T_0_i.rot.mat[:3, 2]
                p_i = T_0_i.trans
                J[node][:3, idx] = np.cross(z_hat_i, p_ee - p_i)
                J[node][3:, idx] = z_hat_i
        return J

    def euclidean_cost_hessian(self, J: dict, K: dict, r: dict):
        """
        Based on 'Solving Inverse Kinematics Using Exact Hessian Matrices', Erleben, 2019
        :param J: dictionary of linear velocity kinematic Jacobians
        :param K: dictionary of tensors representing second order derivative information
        :param r: dictionary where each value for key ee is goal_ee - F_ee(theta)
        :return:
        """
        H = 0
        for e in J.keys():
            J_e = J[e]
            N = J_e.shape[1]
            H += J_e.T @ J_e
            # TODO: Try with einsum for speed, maybe?
            for idx in range(N):
                for jdx in range(idx, N):
                    dH = K[e][:, idx, jdx].T @ r[e]
                    H[idx, jdx] -= dH
                    if idx != jdx:
                        H[jdx, idx] -= dH
        return H

    def hessian_linear_symb(
        self,
        joint_angles: dict,
        J=None,
        query_frame: str = "",
        pose_term=False,
        ee_keys=None,
    ) -> ArrayLike:
        """
        Calculates the Hessian at query_frame geometrically.
        """
        # dZ = np.array([0., 0., 1.])  # For the pose_term = True case
        if J is None:
            J = self.jacobian(joint_angles, pose_term=pose_term)
        kinematic_map = self.kinematic_map[ROOT]  # get map to all nodes from root

        if ee_keys is None:
            end_effector_nodes = []
            for ee in self.end_effectors:  # get p nodes in end-effectors
                if ee[0][0] == MAIN_PREFIX:
                    end_effector_nodes += [ee[0]]
                if ee[1][0] == MAIN_PREFIX:
                    end_effector_nodes += [ee[1]]
        else:
            end_effector_nodes = ee_keys

        N = len(joint_angles)
        M = 3  # 3 translation
        H = {}
        # Ts = self.get_all_poses_symb(joint_angles)
        Ts = self.get_all_poses(joint_angles)
        for ee in end_effector_nodes:
            J_ee = J[ee]
            H_ee = np.zeros((M, N, N), dtype=object)
            ee_path = kinematic_map[ee][1:]

            visited = []

            for joint in ee_path:
                visited += [joint]
                jdx = int(joint[1:]) - 1
                for joint_base in visited:
                    idx = int(joint_base[1:]) - 1
                    T_0_base = Ts[
                        list(self.parents.predecessors(joint_base))[0]
                    ].as_matrix()
                    z_hat_base = T_0_base[:3, 2]
                    h = cross_symb(z_hat_base, J_ee[0:3, jdx])
                    H_ee[:, idx, jdx] = h
                    H_ee[:, jdx, idx] = H_ee[:, idx, jdx]

            H[ee] = H_ee
        return H


if __name__ == "__main__":
    from graphik.utils.roboturdf import load_ur10, load_kuka, load_schunk_lwa4d

    robot, graph = load_schunk_lwa4d()
    q = robot.random_configuration()
    q = robot.random_configuration()
    # T = robot.get_pose(q, "p6")
    # print(robot.get_pose(q, "p6"))
    # print(robot.pose_exp(q, "p6"))
    # print(robot.get_jacobian(q, ["p6"])["p6"])
    # print("---------------------------")
    # print(SE3.adjoint(T.inv()).dot(robot.jacobian(q, ["p6"])["p6"]))
    # print("---------------------------")
    # print(robot.jacobian(q, ["p6"])["p6"] - robot.get_jacobian(q, ["p6"])["p6"])
