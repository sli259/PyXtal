from pymatgen.core.structure import Molecule
from pymatgen.core.operations import SymmOp
from pymatgen.symmetry.analyzer import PointGroupAnalyzer
from pymatgen.symmetry.analyzer import generate_full_symmops
import numpy as np
from numpy.linalg import eigh
from numpy.linalg import det
from copy import deepcopy
from math import fabs
from random import random
from random import choice as choose
from matrix import *
from structure import get_wyckoff_symmetry

#from ase.build import molecule

identity = np.array([[1,0,0],[0,1,0],[0,0,1]])
inversion = np.array([[-1,0,0],[0,-1,0],[0,0,-1]])

def get_inertia_tensor(mol):
    '''
    Calculate the symmetric inertia tensor for a Molecule object
    '''
    mo = mol.get_centered_molecule()
    # Initialize elements of the inertia tensor
    I11 = I22 = I33 = I12 = I13 = I23 = 0.0
    for i in range(len(mo)):
        x, y, z = mo.cart_coords[i]
        m = mo[i].specie.number
        I11 += m * (y ** 2 + z ** 2)
        I22 += m * (x ** 2 + z ** 2)
        I33 += m * (x ** 2 + y ** 2)
        I12 += -m * x * y
        I13 += -m * x * z
        I23 += -m * y * z
    return np.array([[I11, I12, I13],
                  [I12, I22, I23],
                  [I13, I23, I33]])

def get_moment_of_inertia(mol, axis, scale=1.0):
    '''
    Calculate the moment of inertia of a molecule about an axis
    scale: changes the length scale of the molecule. Used to compare symmetry
        axes for equivalence. Defaults to 1
    '''
    #convert axis to unit vector
    axis = axis / np.linalg.norm(axis)
    moment = 0
    for i, a in enumerate(mol):
        v = a.coords
        moment += (scale * np.linalg.norm(np.cross(axis, v)) ) ** 2
    return moment

def reoriented_molecule(mol, nested=False):
    '''
    Return a molecule reoriented so that its principle axes
    are aligned with the identity matrix, and the matrix P
    used to rotate the molecule into this orientation
    '''
    def reorient(mol):
        new_mol = mol.get_centered_molecule()
        A = get_inertia_tensor(new_mol)
        #Store the eigenvectors of the inertia tensor
        P = np.transpose(eigh(A)[1])
        if det(P) < 0:
            P[0] *= -1
        #reorient the molecule
        P = SymmOp.from_rotation_and_translation(P,[0,0,0])
        new_mol.apply_operation(P)
        #Our molecule should never be inverted during reorientation.
        if det(P.rotation_matrix) < 0:
            print("Error: inverted reorientation applied.")
        return new_mol, P
    #If needed, recursively apply reorientation (due to numerical errors)
    iterations = 1
    max_iterations = 100
    new_mol, P = reorient(mol)
    while iterations < max_iterations:
        is_okay = True
        for i in range(3):
            for j in range(3):
                x = eigh(get_inertia_tensor(new_mol))[1][i][j]
                okay = True
                if i == j:
                    #Check that diagonal elements are 0 or 1
                    if (not np.isclose(x, 0)) and (not np.isclose(x, 1)):
                        okay = False
                else:
                    #Check that off-diagonal elements are 0
                    if (not np.isclose(x, 0)):
                        okay = False
        if okay is False:
            #If matrix is not diagonal with 1's and/or 0's, reorient
            new_mol, Q = reorient(new_mol)
            P = Q*P
            iterations += 1
        elif okay is True:
            break
    if iterations == max_iterations:
        print("Error: Could not reorient molecule after "+str(max_iterations)+" attempts")
        print(new_mol)
        print(get_inertia_tensor(new_mol))
        return False
    return new_mol, P

def get_symmetry(mol, already_oriented=False):
    '''
    Return a list of SymmOps for a molecule's point symmetry
    already_oriented: whether or not the principle axes of mol are already reoriented 
    '''
    pga = PointGroupAnalyzer(mol)
    #Handle linear molecules
    if '*' in pga.sch_symbol:
        if already_oriented == False:
            #Reorient the molecule
            oriented_mol, P = reoriented_molecule(mol)
            pga = PointGroupAnalyzer(oriented_mol)
        pg = pga.get_pointgroup()
        symm_m = []
        for op in pg:
            symm_m.append(op)
        #Add 12-fold  and reflections in place of ininitesimal rotation
        for axis in [[1,0,0],[0,1,0],[0,0,1]]:
            op = SymmOp.from_rotation_and_translation(aa2matrix(axis, pi/6), [0,0,0])
            if pga.is_valid_op(op):
                symm_m.append(op)
                #Any molecule with infinitesimal symmetry is linear;
                #Thus, it possess mirror symmetry for any axis perpendicular
                #To the rotational axis. pymatgen does not add this symmetry
                #for all linear molecules - for example, hydrogen
                if axis == [1,0,0]:
                    symm_m.append(SymmOp.from_xyz_string('x,-y,z'))
                    symm_m.append(SymmOp.from_xyz_string('x,y,-z'))
                    r = SymmOp.from_xyz_string('-x,y,-z')
                    '''if pga.is_valid_op(r):
                        symm_m.append(r)'''
                elif axis == [0,1,0]:
                    symm_m.append(SymmOp.from_xyz_string('-x,y,z'))
                    symm_m.append(SymmOp.from_xyz_string('x,y,-z'))
                    r = SymmOp.from_xyz_string('-x,-y,z')
                    '''if pga.is_valid_op(r):
                        symm_m.append(r)'''
                elif axis == [0,0,1]:
                    symm_m.append(SymmOp.from_xyz_string('-x,y,z'))
                    symm_m.append(SymmOp.from_xyz_string('x,-y,z'))
                    r = SymmOp.from_xyz_string('x,-y,-z')
                    '''if pga.is_valid_op(r):
                        symm_m.append(r)'''
                #Generate a full list of SymmOps for the molecule's pointgroup
                symm_m = generate_full_symmops(symm_m, 1e-3)
                break
        #Reorient the SymmOps into mol's original frame
        if not already_oriented:
            new = []
            for op in symm_m:
                new.append(P.inverse*op*P)
            return new
        elif already_oriented:
            return symm_m
    #Handle nonlinear molecules
    else:
        pg = pga.get_pointgroup()
        symm_m = []
        for op in pg:
            symm_m.append(op)
        return symm_m

def orientation_in_wyckoff_position(mol, sg, index, randomize=True,
    exact_orientation=False, already_oriented=False):
    '''
    Tests if a molecule meets the symmetry requirements of a Wyckoff position.
    If it does, return the rotation matrix needed. Otherwise, returns False.

    args:
        mol: pymatgen.core.structure.Molecule object. Orientation is arbitrary
        sg: the spacegroup to check
        index: the index of the Wyckoff position within the sg to check
        randomize: whether or not to apply a random rotation consistent with
            the symmetry requirements.
        exact_orientation: whether to only check compatibility for the provided
            orientation of the molecule. Used within general case for checking.
            If True, this function only returns True or False
    '''
    #Obtain the Wyckoff symmetry
    symm_w = get_wyckoff_symmetry(sg, molecular=True)[index][0]
    #Check exact orientation
    if exact_orientation is True:
        mo = deepcopy(mol)
        pga = PointGroupAnalyzer(mo)
        valid = True
        for op in symm_w:
            if not pga.is_valid_op(op):
                valid = False
        if valid is True:
            return True
        elif valid is False:
            return False
    #Obtain molecular symmetry, exact_orientation==False
    symm_m = get_symmetry(mol, already_oriented=already_oriented)
    #Store OperationAnalyzer objects for each SymmOp
    opa_w = []
    for op_w in symm_w:
        opa_w.append(OperationAnalyzer(op_w))
    opa_m = []
    for op_m in symm_m:
        opa_m.append(OperationAnalyzer(op_m))
    '''#Add opposite direction for 2-fold rotations
    copy = deepcopy(opa_m)
    for opa in copy:
        if opa.type == "rotation" and opa.order == 2:
            symm_m.append(opa.op)
            opa2 = deepcopy(opa)
            opa2.axis = [opa.axis[0]*-1, opa.axis[1]*-1, opa.axis[2]*-1]
            opa_m.append(opa2)'''
    #Check for constraints from the Wyckoff symmetry...
    #If we find ANY two constraints (SymmOps with unique axes), the molecule's
    #point group MUST contain SymmOps which can be aligned to these particular
    #constraints. However, there may be multiple compatible orientations of the
    #molecule consistent with these constraints
    constraint1 = None
    constraint2 = None
    for i, op_w in enumerate(symm_w):
        if opa_w[i].axis is not None:
            constraint1 = opa_w[i]
            for j, op_w in enumerate(symm_w):
                if opa_w[j].axis is not None:
                    dot = np.dot(opa_w[i].axis, opa_w[j].axis)
                    if (not np.isclose(dot, 1, rtol=.01)) and (not np.isclose(dot, -1, rtol=.01)):
                        constraint2 = opa_w[j]
                        break
            break
    #Indirectly store the angle between the constraint axes
    if (constraint1 is not None
        and constraint2 is not None):
        dot_w = np.dot(constraint1.axis, constraint2.axis)
    #Store corresponding symmetry elements of the molecule
    constraints_m = []
    if constraint1 is not None:
        for i, opa1 in enumerate(opa_m):
            if opa1.is_conjugate(constraint1):
                constraints_m.append([opa1, []])
                #Generate 2nd constraint in opposite direction
                extra = deepcopy(opa1)
                extra.axis = [opa1.axis[0]*-1, opa1.axis[1]*-1, opa1.axis[2]*-1]
                constraints_m.append([extra, []])
    #Generate 2nd consistent constraints
    if constraint2 is not None:
        for i, c in enumerate(constraints_m):
            opa1 = c[0]
            for j, opa2 in enumerate(opa_m):
                if opa2.is_conjugate(constraint2):
                    dot_m = np.dot(opa1.axis, opa2.axis)
                    #Ensure that the angles are equal
                    if np.isclose(dot_m, dot_w, rtol=.01) or np.isclose(dot_m, -dot_w, rtol=.01):
                        constraints_m[i][1].append(opa2)
                        #Generate 2nd constraint in opposite direction
                        extra = deepcopy(opa2)
                        extra.axis = [opa2.axis[0]*-1, opa2.axis[1]*-1, opa2.axis[2]*-1]
                        constraints_m[i][1].append(extra)

    '''print("-----")
    x = 0
    for c in constraints_m:
        if len(c[1]) == 0:
            x += 1
        else:
            x += len(c[1])
    print(x)'''

    #Eliminate redundancy for 1st constraint
    list_i = list(range(len(constraints_m)))
    list_j = list(range(len(constraints_m)))
    copy = deepcopy(constraints_m)
    for i , c1 in enumerate(copy):
        if i in list_i:
            for j , c2 in enumerate(copy):
                if i > j and j in list_j and j in list_i:
                    #Check if axes are colinear
                    if np.isclose(np.dot(c1[0].axis, c2[0].axis), 1, rtol=.01):
                        list_i.remove(j)
                        list_j.remove(j)
                    else:# np.isclose(np.dot(c1[0].axis, c2[0].axis), -1, rtol=.01):
                        cond1 = False
                        cond2 = False
                        for opa in opa_m:
                            if opa.type == "rotation":
                                op = opa.op
                                if np.isclose(np.dot(op.operate(c1[0].axis), c2[0].axis), 1, rtol=.05):
                                    cond1 = True
                                if np.isclose(np.dot(op.operate(c2[0].axis), c1[0].axis), 1, rtol=.05):
                                    cond2 = True
                        if cond1 is True and cond2 is True:
                            list_i.remove(j)
                            list_j.remove(j)
                    '''else:
                        #Compare moments of inertia about axes
                        m1_a = get_moment_of_inertia(mol, c1[0].axis)
                        m2_a = get_moment_of_inertia(mol, c2[0].axis)
                        m1_b = get_moment_of_inertia(mol, c1[0].axis, scale=2.0)
                        m2_b = get_moment_of_inertia(mol, c2[0].axis, scale=2.0)
                        if np.isclose(m1_a, m2_a, rtol=1e-2) and np.isclose(m1_b, m2_b, rtol=1e-2):
                            list_i.remove(j)
                            list_j.remove(j)  '''              
    c_m = deepcopy(constraints_m)
    constraints_m = []
    for i in list_i:
        constraints_m.append(c_m[i])

    '''x = 0
    for c in constraints_m:
        if len(c[1]) == 0:
            x += 1
        else:
            x += len(c[1])
    print(x)'''

    #Eliminate redundancy for second constraint
    for k, c in enumerate(constraints_m):
        if c[1] != []:
            list_i = list(range(len(c[1])))
            list_j = list(range(len(c[1])))
            for i, c1 in enumerate(c[1]):
                if i in list_i:
                    for j, c2 in enumerate(c[1]):
                        if j > i and j in list_j and j in list_i:
                            #check if c1 and c2 are symmetrically equivalent
                            #Check if axes are colinear
                            if np.isclose(np.dot(c1.axis, c2.axis), 1, rtol=.01):
                                list_i.remove(j)
                                list_j.remove(j)
                            else:# np.isclose(np.dot(c1.axis, c2.axis), -1, rtol=.01):
                                cond1 = False
                                cond2 = False
                                for opa in opa_m:
                                    if opa.type == "rotation":
                                        op = opa.op
                                        if np.isclose(np.dot(op.operate(c1.axis), c2.axis), 1, rtol=.01):
                                            cond1 = True
                                        if np.isclose(np.dot(op.operate(c2.axis), c1.axis), 1, rtol=.01):
                                            cond2 = True
                                if cond1 is True and cond2 is True:
                                    list_i.remove(j)
                                    list_j.remove(j)
                        '''else:
                            #calculate moments of inertia about both axes
                            m1_a = get_moment_of_inertia(mol, c1.axis)
                            m2_a = get_moment_of_inertia(mol, c2.axis)
                            m1_b = get_moment_of_inertia(mol, c1.axis, scale=2.0)
                            m2_b = get_moment_of_inertia(mol, c2.axis, scale=2.0)
                            if np.isclose(m1_a, m2_a, rtol=1e-2) and np.isclose(m1_b, m2_b, rtol=1e-2):
                                list_i.remove(j)
                                list_j.remove(j)'''
            '''c_m = deepcopy(c[1])
            constraints_m[k][1] = []
            for i in list_i:
                constraints_m[k][1].append(c_m[i])'''

    '''#Debug
    x = 0
    for c in constraints_m:
        if len(c[1]) == 0:
            x += 1
        else:
            x += len(c[1])
    print(x)'''

    '''#Debug
    for i, c1 in enumerate(constraints_m):
        axis1 = c1[0].axis
        for j, c2 in enumerate(constraints_m):
            axis2 = c2[0].axis
            if j > i:
                #Compare axes
                print(axis1, axis2)
                max = -2
                for opa in opa_m:
                    if opa.type == "rotation":
                        op = opa.op
                        dot = np.dot(op.operate(axis1), axis2)
                        if dot > max:
                            max = dot
                        print(opa)
                print(max)'''

    '''#Debug
    print("========")
    for c in constraints_m:
        print("---")
        print(c[0])
        print(c[1])'''

    '''#Look for 2-fold rotations; if found, add extra orientation
    #in opposite direction.
    #Loop over constraint1's
    print(len(constraints_m))
    copy = deepcopy(constraints_m)
    for i , c1 in enumerate(copy):
        if c1[0].type == "rotation" and c1[0].order == 2:
            c = deepcopy(c1)
            c[0].axis *= -1
            constraints_m.append(c)
    #Loop over constraint2's
    copy = deepcopy(constraints_m)
    for i , c1 in enumerate(copy):
        for j, c2 in enumerate(c1[1]):
            if c2.type == "rotation" and c2.order == 2:
                c = deepcopy(c2)
                c.axis *= -1
                constraints_m[i][1].append(c)
    print(len(constraints_m))'''

    #Generate orientations consistent with the possible constraints
    orientations = []
    #Loop over molecular constraint sets
    for c1 in constraints_m:
        v1 = c1[0].axis
        for i, x in enumerate(v1):
            if np.isclose(x, 0):
                v1[i] = 0
        v2 = constraint1.axis
        T = rotate_vector(v1, v2)
        #Loop over second molecular constraints
        for opa in c1[1]:
            v = constraint1.axis
            a = angle(np.dot(T, opa.axis), constraint2.axis)
            R = aa2matrix(v, a)
            T2 = np.dot(R, T)
            #T2 = np.dot(np.linalg.inv(R), np.dot(T, R))
            a = angle(np.dot(T2, opa.axis), constraint2.axis)
            if not np.isclose(a, 0, rtol=.01):
                T2 = np.dot(np.linalg.inv(R), T)
            a = angle(np.dot(T2, opa.axis), constraint2.axis)
            if not np.isclose(a, 0, rtol=.01):
                print("Error: Generated incorrect rotation: "+str(a))
            orientations.append(T2)
        #If there is only one constraint
        if c1[1] == []:
            if randomize is True:
                a = rand()*2*pi
                R = aa2matrix(constraint1.axis, a)
                T2 = np.dot(R, T)
                #T2 = np.dot(np.linalg.inv(R), np.dot(T, R))
                orientations.append(T2)
            else:
                orientations.append(T)
    #Ensure the identity orientation is checked if no constraints are found
    if constraints_m == []:
        if randomize is True:
            R = aa2matrix(1,1,random=True)
            orientations.append(R)
        elif randomize is False:
            orientations.append(np.identity(3))

    #Remove redundancy from orientations
    list_i = list(range(len(orientations)))
    list_j = list(range(len(orientations)))
    for i , m1 in enumerate(orientations):
        if i in list_i:
            for j , m2 in enumerate(orientations):
                if i > j and j in list_j and j in list_i:
                    cond1 = False
                    cond2 = False
                    #Check if m1 and m2 are symmetrically equivalent
                    for opa in opa_m:
                        op = opa.op
                        m = op.rotation_matrix
                        if np.allclose(np.dot(m1, m), m2, rtol=.01):
                            cond1 = True
                        if np.allclose(np.dot(m2, m), m1, rtol=.01):
                            cond2 = True
                    if cond1 is True and cond2 is True:
                        list_i.remove(j)
                        list_j.remove(j)
    copy = deepcopy(orientations)
    orientations = []
    for i in list_i:
        orientations.append(copy[i])

    '''#Debug
    for o in orientations:
        print("-----")
        op = SymmOp.from_rotation_and_translation(o, [0,0,0])
        mo = deepcopy(mol)
        mo.apply_operation(op)
        symm = get_symmetry(mo)
        opas = []
        for op in symm:
            opas.append(OperationAnalyzer(op))
        for opa in opas:
            print(opa)'''

    #Check each of the found orientations for consistency with the Wyckoff pos.
    #If consistent, put into an array of valid orientations
    allowed = []
    for o in orientations:
        op = SymmOp.from_rotation_and_translation(o,[0,0,0])
        mo = deepcopy(mol)
        mo.apply_operation(op)
        if orientation_in_wyckoff_position(mo, sg, index, exact_orientation=True, already_oriented=already_oriented) is True:
            allowed.append(op)
    #Return the array of allowed orientations. If there are none, return False
    if allowed == []:
        return False
    else:
        return allowed

#Test Functionality
if __name__ == "__main__":
#---------------------------------------------------
    #Test cases: water, methane, and c60 via pymatgen
    h2o = Molecule.from_file('xyz/water.xyz')
    pga_h2o = PointGroupAnalyzer(h2o)
    pg_h2o = pga_h2o.get_pointgroup()
    c60 = Molecule.from_file('xyz/C60-0.xyz')
    pga_c60 = PointGroupAnalyzer(c60)
    pg_c60 = pga_c60.get_pointgroup()
    h2 = Molecule.from_file('xyz/hydrogen.xyz')
    pga_h2 = PointGroupAnalyzer(h2)
    pg_h2 = pga_h2.get_pointgroup()
    ch4 = Molecule.from_file('xyz/methane.xyz')
    pga_ch4 = PointGroupAnalyzer(ch4)
    pg_ch4 = pga_ch4.get_pointgroup()
    rand_mol = Molecule.from_file('xyz/random.xyz')
    pga_rand_mol = PointGroupAnalyzer(rand_mol)
    pg_rand_mol = pga_rand_mol.get_pointgroup()

    #Testing water
    mol = deepcopy(c60)
    print("Original molecule:")
    print(mol)
    print()
    #Apply random rotation to avoid lucky results
    R = aa2matrix(1,1,random=True)
    R_op = SymmOp.from_rotation_and_translation(R,[0,0,0])
    mol.apply_operation(R_op)
    print("Rotated molecule:")
    print(mol)
    print("============================================")

    pga = PointGroupAnalyzer(mol)
    mol = pga.symmetrize_molecule()['sym_mol']    

    #orientation_in_wyckoff_position(mol, sg, WP's index in sg)
    #returns a list of orientations consistent with the WP's symmetry.
    #We can choose any of these orientations at random using np.random.choice
    #To use an orientation, do mol.apply_operation(orientation)
    #Spacegroup WP 24l (index 2) in sg 221 has m.. symmetry
    allowed =  orientation_in_wyckoff_position(mol, 221, 2, randomize=True)
    print("Found "+str(len(allowed))+" orientations:")
    print("------------------------------")
    for op in allowed:
        mo = deepcopy(mol)
        mo.apply_operation(op)
        print()
        print(mo)
