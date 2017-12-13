# -*- coding: utf-8 -*-
"""
Created on Mon Dec  4 20:10:27 2017

@author: marco musy
"""
from __future__ import division, print_function
from glob import glob
import os, sys, types
import numpy as np
from colors import getColor
import vtk
import time


vtkMV = vtk.vtkVersion().GetVTKMajorVersion() > 5
def setInput(vtkobj, p):
    if vtkMV: vtkobj.SetInputData(p)
    else: vtkobj.SetInput(p)


####################################### LOADER
def load(filesOrDirs, c='gold', alpha=0.2, 
          wire=False, bc=None, edges=False, legend=True, texture=None):
    '''Returns a vtkActor from reading a file or directory. 
       Optional args:
       c,     color in RGB format, hex, symbol or name
       alpha, transparency (0=invisible)
       wire,  show surface as wireframe
       bc,    backface color of internal surface
       legend, text to show on legend, if True picks filename.
    '''
    acts = []
    if isinstance(legend, int): legend = bool(legend)
    for fod in sorted(glob(filesOrDirs)):
        if os.path.isfile(fod): 
            a = _loadFile(fod, c, alpha, wire, bc, edges, legend, texture)
            acts.append(a)
        elif os.path.isdir(fod):
            acts = _loadDir(fod, c, alpha, wire, bc, edges, legend, texture)
    if not len(acts):
        printc(('Cannot find:', filesOrDirs), c=1)
        exit(0) 
    if len(acts) == 1: return acts[0]
    else: return acts


def _loadFile(filename, c, alpha, wire, bc, edges, legend, texture):
    fl = filename.lower()
    if '.xml' in fl or '.xml.gz' in fl: # Fenics tetrahedral mesh file
        actor = _loadXml(filename, c, alpha, wire, bc, edges, legend)
    elif '.pcd' in fl:                  # PCL point-cloud format
        actor = _loadPCD(filename, c, alpha, legend)
    else:
        poly = _loadPoly(filename)
        if not poly:
            printc(('Unable to load', filename), c=1)
            return False
        if legend is True: legend = os.path.basename(filename)
        actor = makeActor(poly, c, alpha, wire, bc, edges, legend, texture)
        if '.txt' in fl or '.xyz' in fl: 
            actor.GetProperty().SetPointSize(4)
    return actor
    
def _loadDir(mydir, c, alpha, wire, bc, edges, legend, texture):
    acts = []
    for ifile in sorted(os.listdir(mydir)):
        _loadFile(mydir+'/'+ifile, c, alpha, wire, bc, edges, legend, texture)
    return acts

def _loadPoly(filename):
    '''Return a vtkPolyData object, NOT a vtkActor'''
    if not os.path.exists(filename): 
        printc(('Cannot find file', filename), c=1)
        exit(0)
    fl = filename.lower()
    if   '.vtk' in fl: reader = vtk.vtkPolyDataReader()
    elif '.ply' in fl: reader = vtk.vtkPLYReader()
    elif '.obj' in fl: reader = vtk.vtkOBJReader()
    elif '.stl' in fl: reader = vtk.vtkSTLReader()
    elif '.byu' in fl or '.g' in fl: reader = vtk.vtkBYUReader()
    elif '.vtp' in fl: reader = vtk.vtkXMLPolyDataReader()
    elif '.vts' in fl: reader = vtk.vtkXMLStructuredGridReader()
    elif '.vtu' in fl: reader = vtk.vtkXMLUnstructuredGridReader()
    elif '.txt' in fl: reader = vtk.vtkParticleReader() # (x y z scalar) 
    elif '.xyz' in fl: reader = vtk.vtkParticleReader()
    else: reader = vtk.vtkDataReader()
    reader.SetFileName(filename)
    reader.Update()
    if '.vts' in fl: # structured grid
        gf = vtk.vtkStructuredGridGeometryFilter()
        gf.SetInputConnection(reader.GetOutputPort())
        gf.Update()
        poly = gf.GetOutput()
    elif '.vtu' in fl: # unstructured grid
        gf = vtk.vtkGeometryFilter()
        gf.SetInputConnection(reader.GetOutputPort())
        gf.Update()    
        poly = gf.GetOutput()
    else: poly = reader.GetOutput()
    
    if not poly: 
        printc(('Unable to load', filename), c=1)
        return False
    
    mergeTriangles = vtk.vtkTriangleFilter()
    setInput(mergeTriangles, poly)
    mergeTriangles.Update()
    poly = mergeTriangles.GetOutput()
    return poly


def _loadXml(filename, c, alpha, wire, bc, edges, legend):
    '''Reads a Fenics/Dolfin file format'''
    if not os.path.exists(filename): 
        printc(('Cannot find file', filename), c=1)
        exit(0)
    try:
        import xml.etree.ElementTree as et
        if '.gz' in filename:
            import gzip
            inF = gzip.open(filename, 'rb')
            outF = open('/tmp/filename.xml', 'wb')
            outF.write( inF.read() )
            outF.close()
            inF.close()
            tree = et.parse('/tmp/filename.xml')
        else: tree = et.parse(filename)
        coords, connectivity = [], []
        for mesh in tree.getroot():
            for elem in mesh:
                for e in elem.findall('vertex'):
                    x = float(e.get('x'))
                    y = float(e.get('y'))
                    z = float(e.get('z'))
                    coords.append([x,y,z])
                for e in elem.findall('tetrahedron'):
                    v0 = int(e.get('v0'))
                    v1 = int(e.get('v1'))
                    v2 = int(e.get('v2'))
                    v3 = int(e.get('v3'))
                    connectivity.append([v0,v1,v2,v3])
        points = vtk.vtkPoints()
        for p in coords: points.InsertNextPoint(p)

        ugrid = vtk.vtkUnstructuredGrid()
        ugrid.SetPoints(points)
        cellArray = vtk.vtkCellArray()
        for itet in range(len(connectivity)):
            tetra = vtk.vtkTetra()
            for k,j in enumerate(connectivity[itet]):
                tetra.GetPointIds().SetId(k, j)
            cellArray.InsertNextCell(tetra)
        ugrid.SetCells(vtk.VTK_TETRA, cellArray)
        # 3D cells are mapped only if they are used by only one cell,
        #  i.e., on the boundary of the data set
        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputConnection(ugrid.GetProducerPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetInterpolationToFlat()
        actor.GetProperty().SetColor(getColor(c))
        actor.GetProperty().SetOpacity(alpha/2.)
        #actor.GetProperty().VertexVisibilityOn()
        if edges: actor.GetProperty().EdgeVisibilityOn()
        if wire:  actor.GetProperty().SetRepresentationToWireframe()
        vpts = vtk.vtkPointSource()
        vpts.SetNumberOfPoints(len(coords))
        vpts.Update()
        vpts.GetOutput().SetPoints(points)
        pts_act = makeActor(vpts.GetOutput(), c='b', alpha=alpha)
        pts_act.GetProperty().SetPointSize(3)
        pts_act.GetProperty().SetRepresentationToPoints()
        actor2 = makeAssembly([pts_act, actor])
        if legend: setattr(actor2, 'legend', legend)
        if legend is True: 
            setattr(actor2, 'legend', os.path.basename(filename))
        return actor2
    except:
        printc(("Cannot parse xml file. Skip.", filename), c=1)
        return False
 

def _loadPCD(filename, c, alpha, legend):
    '''Return vtkActor from Point Cloud file format'''            
    if not os.path.exists(filename): 
        printc(('Cannot find file', filename), 'red')
        exit(0)
    f = open(filename, 'r')
    lines = f.readlines()
    f.close()
    start = False
    pts = []
    N, expN = 0, 0
    for text in lines:
        if start:
            if N >= expN: break
            l = text.split()
            pts.append([float(l[0]),float(l[1]),float(l[2])])
            N += 1
        if not start and 'POINTS' in text:
            expN= int(text.split()[1])
        if not start and 'DATA ascii' in text:
            start = True
    if expN != N:
        printc(('Mismatch in pcd file', expN, len(pts)), 'red')
    src = vtk.vtkPointSource()
    src.SetNumberOfPoints(len(pts))
    src.Update()
    poly = src.GetOutput()
    for i,p in enumerate(pts): poly.GetPoints().SetPoint(i, p)
    if not poly:
        printc(('Unable to load', filename), 'red')
        return False
    actor = makeActor(poly, getColor(c), alpha)
    actor.GetProperty().SetPointSize(4)
    if legend: setattr(actor, 'legend', legend)
    if legend is True: setattr(actor, 'legend', os.path.basename(filename))
    return actor
    
    
##############################################################################
def makeActor(poly, c='gold', alpha=0.5, 
              wire=False, bc=None, edges=False, legend=None, texture=None):
    '''Return a vtkActor from an input vtkPolyData, optional args:
       c,       color in RGB format, hex, symbol or name
       alpha,   transparency (0=invisible)
       wire,    show surface as wireframe
       bc,      backface color of internal surface
       edges,   show edges as line on top of surface
       legend   optional string
       texture  jpg file name of surface texture, eg. 'metalfloor1'
    '''
    dataset = vtk.vtkPolyDataNormals()
    setInput(dataset, poly)
    dataset.SetFeatureAngle(60.0)
    dataset.ComputePointNormalsOn()
    dataset.ComputeCellNormalsOn()
    dataset.FlipNormalsOff()
    dataset.ConsistencyOn()
    dataset.Update()
    mapper = vtk.vtkPolyDataMapper()

#    mapper.ScalarVisibilityOff()    
#    mapper.ScalarVisibilityOn ()
#    mapper.SetScalarMode(2)
#    mapper.SetColorModeToDefault()
#    mapper.SelectColorArray("Colors")
#    mapper.SetScalarRange(0,255)
#    mapper.SetScalarModeToUsePointData ()
#    mapper.UseLookupTableScalarRangeOff ()

    setInput(mapper, dataset.GetOutput())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    
    c = getColor(c)
    actor.GetProperty().SetColor(c)
    actor.GetProperty().SetOpacity(alpha)

    actor.GetProperty().SetSpecular(0)
    actor.GetProperty().SetSpecularColor(c)
    actor.GetProperty().SetSpecularPower(1)

    actor.GetProperty().SetAmbient(0)
    actor.GetProperty().SetAmbientColor(c)

    actor.GetProperty().SetDiffuse(1)
    actor.GetProperty().SetDiffuseColor(c)

    if edges: actor.GetProperty().EdgeVisibilityOn()
    if wire: actor.GetProperty().SetRepresentationToWireframe()
    if texture: assignTexture(actor, texture)
    if bc: # defines a specific color for the backface
        backProp = vtk.vtkProperty()
        backProp.SetDiffuseColor(getColor(bc))
        backProp.SetOpacity(alpha)
        actor.SetBackfaceProperty(backProp)

    assignPhysicsMethods(actor)    
    assignConvenienceMethods(actor, legend)    
    return actor


def makeAssembly(actors, legend=None):
    '''Treat many actors as a single new actor'''
    assembly = vtk.vtkAssembly()
    for a in actors: assembly.AddPart(a)
    setattr(assembly, 'legend', legend) 
#    if hasattr(actors[0], 'legend'): assembly.legend = actors[0].legend
    assignPhysicsMethods(assembly)
    return assembly


def assignConvenienceMethods(actor, legend):
    
    if not hasattr(actor, 'legend'):
        setattr(actor, 'legend', legend)

    def _frotate(self, angle, axis, rad=False): 
        return rotate(self, angle, axis, rad)
    actor.rotate = types.MethodType( _frotate, actor )

    def _frotateX(self, angle, rad=False): 
        return rotate(self, angle, [1,0,0], rad)
    actor.rotateX = types.MethodType( _frotateX, actor )

    def _frotateY(self, angle, rad=False): 
        return rotate(self, angle, [0,1,0], rad)
    actor.rotateY = types.MethodType( _frotateY, actor )

    def _frotateZ(self, angle, rad=False): 
        return rotate(self, angle, [0,0,1], rad)
    actor.rotateZ = types.MethodType( _frotateZ, actor )

    def _fclone(self, c='gold', alpha=1, wire=False, bc=None,
                edges=False, legend=None, texture=None): 
        return clone(self, c, alpha, wire, bc, edges, legend, texture)
    actor.clone = types.MethodType( _fclone, actor )

    def _fnormalize(self): return normalize(self)
    actor.normalize = types.MethodType( _fnormalize, actor )

    def _fshrink(self, fraction=0.85): return shrink(self, fraction)
    actor.shrink = types.MethodType( _fshrink, actor )

    def _fcutterw(self): return cutterWidget(self)
    actor.cutterWidget = types.MethodType( _fcutterw, actor )
    
    def _fvisible(self, alpha=1): self.GetProperty().SetOpacity(alpha)
    actor.visible = types.MethodType( _fvisible, actor )
    


def assignPhysicsMethods(actor):
    
    apos = np.array(actor.GetPosition())
    setattr(actor, '_pos',  apos)         # position  
    def _fpos(self, p=None): 
        if p is None: return self._pos
        self.SetPosition(p)
        self._pos = np.array(p)
    actor.pos = types.MethodType( _fpos, actor )

    def _faddpos(self, dp): 
        self.AddPosition(dp)
        self._pos += dp        
    actor.addpos = types.MethodType( _faddpos, actor )

    def _fpx(self, px=None):               # X  
        if px is None: return self._pos[0]
        newp = [px, self._pos[1], self._pos[2]]
        self.SetPosition(newp)
        self._pos = newp
    actor.x = types.MethodType( _fpx, actor )

    def _fpy(self, py=None):               # Y  
        if py is None: return self._pos[1]
        newp = [self._pos[0], py, self._pos[2]]
        self.SetPosition(newp)
        self._pos = newp
    actor.y = types.MethodType( _fpy, actor )

    def _fpz(self, pz=None):               # Z  
        if pz is None: return self._pos[2]
        newp = [self._pos[0], self._pos[1], pz]
        self.SetPosition(newp)
        self._pos = newp
    actor.z = types.MethodType( _fpz, actor )
     
    setattr(actor, '_vel',  np.array([0,0,0]))  # velocity
    def _fvel(self, v=None): 
        if v is None: return self._vel
        self._vel = v
    actor.vel = types.MethodType( _fvel, actor )
    
    def _fvx(self, vx=None):               # VX  
        if vx is None: return self._vel[0]
        newp = [vx, self._vel[1], self._vel[2]]
        self.SetPosition(newp)
        self._vel = newp
    actor.vx = types.MethodType( _fvx, actor )

    def _fvy(self, vy=None):               # VY  
        if vy is None: return self._vel[1]
        newp = [self._vel[0], vy, self._vel[2]]
        self.SetPosition(newp)
        self._vel = newp
    actor.vy = types.MethodType( _fvy, actor )

    def _fvz(self, vz=None):               # VZ  
        if vz is None: return self._vel[2]
        newp = [self._vel[0], self._vel[1], vz]
        self.SetPosition(newp)
        self._vel = newp
    actor.vz = types.MethodType( _fvz, actor )
     
    setattr(actor, '_mass',  1.0)               # mass
    def _fmass(self, m=None): 
        if m is None: return self._mass
        self._mass = m
    actor.mass = types.MethodType( _fmass, actor )

    setattr(actor, '_axis',  np.array([0,0,1]))  # axis
    def _faxis(self, a=None): 
        if a is None: return self._axis
        self._axis = a
    actor.axis = types.MethodType( _faxis, actor )

    setattr(actor, '_omega', 0.0)     # angular velocity
    def _fomega(self, o=None): 
        if o is None: return self._omega
        self._omega = o
    actor.omega = types.MethodType( _fomega, actor )

    def _fmomentum(self): 
        return self._mass * self._vel
    actor.momentum = types.MethodType( _fmomentum, actor )

    def _fgamma(self):                 # Lorentz factor
        v2 = np.sum( self._vel*self._vel )
        return 1./np.sqrt(1. - v2/299792.48**2)
    actor.gamma = types.MethodType( _fgamma, actor )

    return actor ########### >>


######################################################### 
def normalize(actor): 
    cm = getCM(actor)
    coords = getCoordinates(actor)
    if not len(coords) : return
    pts = getCoordinates(actor) - cm
    xyz2 = np.sum(pts * pts, axis=0)
    scale = 1./np.sqrt(np.sum(xyz2)/len(pts))
    actor.SetPosition(0,0,0)
    actor.SetScale(scale, scale, scale)
    poly = getPolyData(actor)
    for i,p in enumerate(pts): 
        poly.GetPoints().SetPoint(i, p)


def clone(actor, c='gold', alpha=0.5, wire=False, bc=None,
          edges=False, legend=None, texture=None): 
    poly = getPolyData(actor)
    if not len(getCoordinates(actor)):
        printc('Limitation: cannot clone textured obj. Returning input.', 'red')
        return actor
    polyCopy = vtk.vtkPolyData()
    polyCopy.DeepCopy(poly)
    a = makeActor(polyCopy, c, alpha, wire, bc, edges, legend, texture)
    return a
    

def rotate(actor, angle, axis, rad=False):
    l = np.linalg.norm(axis)
    if not l: return
    axis /= l
    if rad: angle *= 57.3
    actor.RotateWXYZ(-angle, axis[0], axis[1], axis[2])


def shrink(actor, fraction=0.85):
    poly = getPolyData(actor)
    shrink = vtk.vtkShrinkPolyData()
    setInput(shrink, poly)
    shrink.SetShrinkFactor(fraction)
    shrink.Update()
    mapper = actor.GetMapper()
    setInput(mapper, shrink.GetOutput())


#########################################################
# Useful Functions
######################################################### 
def screenshot(filename='screenshot.png'):
    try:
        import gtk.gdk
        w = gtk.gdk.get_default_root_window().get_screen().get_active_window()
        sz = w.get_size()
        pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, sz[0], sz[1])
        pb = pb.get_from_drawable(w,w.get_colormap(),0,0,0,0, sz[0], sz[1])
        if pb is not None:
            pb.save(filename, "png")
            #print ("Screenshot saved to", filename)
        else: printc("Unable to save the screenshot. Skip.", 'red')
    except:
        printc("Unable to take the screenshot. Skip.", 'red')


def makePolyData(spoints, addLines=True):
    """Try to workout a polydata from points"""
    sourcePoints = vtk.vtkPoints()
    sourceVertices = vtk.vtkCellArray()
    for pt in spoints:
        if len(pt)==3: #it's 3D!
            aid = sourcePoints.InsertNextPoint(pt[0], pt[1], pt[2])
        else:
            aid = sourcePoints.InsertNextPoint(pt[0], pt[1], 0)
        sourceVertices.InsertNextCell(1)
        sourceVertices.InsertCellPoint(aid)
    source = vtk.vtkPolyData()
    source.SetPoints(sourcePoints)
    source.SetVerts(sourceVertices)
    if addLines:
        lines = vtk.vtkCellArray()
        lines.InsertNextCell(len(spoints))
        for i in range(len(spoints)): lines.InsertCellPoint(i)
        source.SetLines(lines)
    source.Update()
    return source


def isInside(poly, point):
    """Return True if point is inside a polydata closed surface"""
    points = vtk.vtkPoints()
    points.InsertNextPoint(point)
    pointsPolydata = vtk.vtkPolyData()
    pointsPolydata.SetPoints(points)
    sep = vtk.vtkSelectEnclosedPoints()
    setInput(sep, pointsPolydata)
    sep.SetSurface(poly)
    sep.Update()
    return sep.IsInside(0)


#################################################################### get stuff
def getPolyData(obj, index=0): 
    '''
    Returns vtkPolyData from an other object (vtkActor, vtkAssembly, int)
    '''
    if   isinstance(obj, list) and len(obj)==1: obj = obj[0]
    if   isinstance(obj, vtk.vtkPolyData): return obj
    elif isinstance(obj, vtk.vtkActor):    return obj.GetMapper().GetInput()
    elif isinstance(obj, vtk.vtkActor2D):  return obj.GetMapper().GetInput()
    elif isinstance(obj, vtk.vtkAssembly):
        cl = vtk.vtkPropCollection()
        obj.GetActors(cl)
        cl.InitTraversal()
        for i in range(index+1):
            act = vtk.vtkActor.SafeDownCast(cl.GetNextProp())
        return act.GetMapper().GetInput()
    printc("Fatal Error in getPolyData(): ", 'red', end='')
    printc(("input is neither a poly nor an actor int or assembly.", [obj]), 'red')
    exit(1)


def getPoint(i, actor):
    poly = getPolyData(actor)
    p = [0,0,0]
    poly.GetPoints().GetPoint(i, p)
    return np.array(p)


def getCoordinates(actors):
    """Return a merged list of coordinates of actors or polys"""
    if not isinstance(actors, list): actors = [actors]
    pts = []
    for i in range(len(actors)):
        apoly = getPolyData(actors[i])
        for j in range(apoly.GetNumberOfPoints()):
            p = [0, 0, 0]
            apoly.GetPoint(j, p)
            pts.append(p)
    return np.array(pts)


def getMaxOfBounds(actor):
    '''Get the maximum dimension of the actor bounding box'''
    poly = getPolyData(actor)
    b = poly.GetBounds()
    maxb = max(abs(b[1]-b[0]), abs(b[3]-b[2]), abs(b[5]-b[4]))
    return maxb


def getCM(actor):
    '''Get the Center of Mass of the actor'''
    if vtkMV: #faster
        cmf = vtk.vtkCenterOfMass()
        setInput(cmf, getPolyData(actor))
        cmf.UseScalarsAsWeightsOff()
        cmf.Update()
        c = cmf.GetCenter()
        return np.array(c)
    else:
        pts = getCoordinates(actor)
        if not len(pts): return np.array([0,0,0])
        return np.mean(pts, axis=0)       


def getVolume(actor):
    '''Get the volume occupied by actor'''
    mass = vtk.vtkMassProperties()
    setInput(mass, getPolyData(actor))
    mass.Update() 
    return mass.GetVolume()


def getArea(actor):
    '''Get the surface area of actor'''
    mass = vtk.vtkMassProperties()
    setInput(mass, getPolyData(actor))
    mass.Update() 
    return mass.GetSurfaceArea()


def assignTexture(actor, name, scale=1, falsecolors=False, mapTo=1):
    '''Assign a texture to actro from file or name in /textures directory'''
    if   mapTo == 1: tmapper = vtk.vtkTextureMapToCylinder()
    elif mapTo == 2: tmapper = vtk.vtkTextureMapToSphere()
    elif mapTo == 3: tmapper = vtk.vtkTextureMapToPlane()
    
    setInput(tmapper, getPolyData(actor))
    if mapTo == 1:  tmapper.PreventSeamOn()
    
    xform = vtk.vtkTransformTextureCoords()
    xform.SetInputConnection(tmapper.GetOutputPort())
    xform.SetScale(scale,scale,scale)
    if mapTo == 1: xform.FlipSOn()
    
    mapper = vtk.vtkDataSetMapper()
    mapper.SetInputConnection(xform.GetOutputPort())
    
    cdir = os.path.dirname(__file__)     
    fn = cdir + '/textures/'+name+".jpg"
    if os.path.exists(name): 
        fn = name
    elif not os.path.exists(fn):
        printc(('Texture', name, 'not found in', cdir+'/textures'), 'red')
        return 
        
    jpgReader = vtk.vtkJPEGReader()
    jpgReader.SetFileName(fn)
    atext = vtk.vtkTexture()
    atext.RepeatOn()
    atext.EdgeClampOff()
    atext.InterpolateOn()
    if falsecolors: atext.MapColorScalarsThroughLookupTableOn()
    atext.SetInputConnection(jpgReader.GetOutputPort())
    actor.GetProperty().SetColor(1,1,1)
    actor.SetMapper(mapper)
    actor.SetTexture(atext)
    
    
def writeVTK(obj, fileoutput):
    wt = vtk.vtkPolyDataWriter()
    setInput(wt, getPolyData(obj))
    wt.SetFileName(fileoutput)
    wt.Write()
    printc(("Saved vtk file:", fileoutput), 'green')
    

########################################################################
def closestPoint(surf, pt, locator=None, N=None, radius=None):
    """
    Find the closest point on a polydata given an other point.
    If N is given, return a list of N ordered closest points.
    If radius is given, pick only within specified radius.
    """
    polydata = getPolyData(surf)
    trgp  = [0,0,0]
    cid   = vtk.mutable(0)
    dist2 = vtk.mutable(0)
    if not locator:
        if N: locator = vtk.vtkPointLocator()
        else: locator = vtk.vtkCellLocator()
        locator.SetDataSet(polydata)
        locator.BuildLocator()
    if N:
        vtklist = vtk.vtkIdList()
        vmath = vtk.vtkMath()
        locator.FindClosestNPoints(N, pt, vtklist)
        trgp_, trgp, dists2 = [0,0,0], [], []
        for i in range(vtklist.GetNumberOfIds()):
            vi = vtklist.GetId(i)
            polydata.GetPoints().GetPoint(vi, trgp_ )
            trgp.append( trgp_ )
            dists2.append(vmath.Distance2BetweenPoints(trgp_, pt))
        dist2 = dists2
    elif radius:
        cell = vtk.mutable(0)
        r = locator.FindClosestPointWithinRadius(pt, radius, trgp, cell, cid, dist2)
        if not r: 
            trgp = pt
            dist2 = 0.0
    else: 
        subid = vtk.mutable(0)
        locator.FindClosestPoint(pt, trgp, cid, subid, dist2)
    return trgp


########################################################################
def cutterWidget(obj, outputname='clipped.vtk', c=(0.2, 0.2, 1), alpha=1, 
                 wire=False, bc=(0.7, 0.8, 1), edges=False, legend=None):
    '''Pop up a box widget to cut parts of actor. Return largest part.'''
    apd = getPolyData(obj)
    planes  = vtk.vtkPlanes()
    planes.SetBounds(apd.GetBounds())
    clipper = vtk.vtkClipPolyData()
    setInput(clipper, apd)
    clipper.SetClipFunction(planes)
    clipper.InsideOutOn()
    clipper.GenerateClippedOutputOn()

    confilter = vtk.vtkPolyDataConnectivityFilter()
    setInput(confilter, clipper.GetOutput())
    confilter.SetExtractionModeToLargestRegion()
    confilter.Update()
    cpd = vtk.vtkCleanPolyData()
    setInput(cpd, confilter.GetOutput())

    cpoly = clipper.GetClippedOutput() # cut away part
    restActor = makeActor(cpoly, c=c, alpha=0.05, wire=1)
    
    actor = makeActor(clipper.GetOutput(), c, alpha, wire, bc, edges, legend)
    actor.GetProperty().SetInterpolationToFlat()

    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    ren.AddActor(actor)
    ren.AddActor(restActor)

    renWin = vtk.vtkRenderWindow()
    renWin.SetSize(800, 800)
    renWin.AddRenderer(ren)
    
    iren = vtk.vtkRenderWindowInteractor()
    iren.SetRenderWindow(renWin)
    istyl = vtk.vtkInteractorStyleSwitch()
    istyl.SetCurrentStyleToTrackballCamera()
    iren.SetInteractorStyle(istyl)
    
    def selectPolygons(object, event): object.GetPlanes(planes)
    boxWidget = vtk.vtkBoxWidget()
    boxWidget.OutlineCursorWiresOn()
    boxWidget.GetSelectedOutlineProperty().SetColor(1,0,1)
    boxWidget.GetOutlineProperty().SetColor(0.1,0.1,0.1)
    boxWidget.GetOutlineProperty().SetOpacity(0.8)
    boxWidget.SetPlaceFactor(1.05)
    boxWidget.SetInteractor(iren)
    setInput(boxWidget, apd)
    boxWidget.PlaceWidget()
    boxWidget.AddObserver("InteractionEvent", selectPolygons)
    boxWidget.On()
    
    printc(("Press X to save file:", outputname), 'blue')
    def cwkeypress(obj, event):
        if obj.GetKeySym() == "X":
            writeVTK(cpd.GetOutput(), outputname)
            
    iren.Initialize()
    iren.AddObserver("KeyPressEvent", cwkeypress)
    iren.Start()
    boxWidget.Off()
    return actor


###################################################################### Video
def openVideo(name='movie.avi', fps=12, duration=None, format="XVID"):
    global _videoname
    global _videoformat
    global _videoduration
    global _fps
    global _frames
    try:
        import cv2 #just check existence
        cv2.__version__
    except:
        print ("openVideo: cv2 not installed? Skip.")
        return
    _videoname = name
    _videoformat = format
    _videoduration = duration
    _fps = float(fps) # if duration is given, will be recalculated
    _frames = []
    if not os.path.exists('/tmp/v'): os.mkdir('/tmp/v')
    for fl in glob("/tmp/v/*.png"): os.remove(fl)
    print ("Video", name, "is open. Press q to continue.")
    
def addFrameVideo():
    global _videoname, _frames
    if not _videoname: return
    fr = '/tmp/v/'+str(len(_frames))+'.png'
    screenshot(fr)
    _frames.append(fr)

def pauseVideo(pause):
    '''insert a pause, in seconds'''
    global _frames
    if not _videoname: return
    fr = _frames[-1]
    n = int(_fps*pause)
    for i in range(n): 
        fr2='/tmp/v/'+str(len(_frames))+'.png'
        _frames.append(fr2)
        os.system("cp -f %s %s" % (fr, fr2))
        
def releaseGif(): #untested
    global _videoname, _frames
    if not _videoname: return
    try: import imageio
    except: 
        print ("release_gif: imageio not installed? Skip.")
        return
    images = []
    for fl in _frames:
        images.append(imageio.imread(fl))
    imageio.mimsave('animation.gif', images)

def releaseVideo():      
    global _videoname, _fps, _videoduration, _videoformat, _frames
    if not _videoname: return
    import cv2
    if _videoduration:
        _fps = len(_frames)/float(_videoduration)
        print ("Recalculated video FPS to", round(_fps,3))
    else: _fps = int(_fps)
    fourcc = cv2.cv.CV_FOURCC(*_videoformat)
    vid = None
    size = None
    for image in _frames:
        if not os.path.exists(image):
            print ('Image not found:', image)
            continue
        img = cv2.imread(image)
        if vid is None:
            if size is None:
                size = img.shape[1], img.shape[0]
            vid = cv2.VideoWriter(_videoname, fourcc, _fps, size, True)
        if size[0] != img.shape[1] and size[1] != img.shape[0]:
            img = cv2.resize(img, size)
        vid.write(img)
    vid.release()
    print ('Video saved as', _videoname)
    _videoname = False


###########################################################################
class ProgressBar: 
    '''Class to print a progress bar with optional text on its right'''
    # import time                        ### Usage example:
    # pb = ProgressBar(0,400, c='red')
    # for i in pb.range():
    #     time.sleep(.1)
    #     pb.print('some message')       # or pb.print(counts=i) 
    def __init__(self, start, stop, step=1, c=None, ETA=True, width=25):
        self.start  = start
        self.stop   = stop
        self.step   = step
        self.color  = c
        self.width  = width
        self.bar    = ""  
        self.percent= 0
        self._counts= 0
        self._oldbar= ""
        self._lentxt= 0
        self._range = range(start, stop, step) 
        self._len   = len(self._range)
        self.clock0 = 0
        self.ETA    = ETA
        self.clock0 = time.time()
        self._update(0)
        
    def print(self, txt='', counts=None):
        if counts: self._update(counts)
        else:      self._update(self._counts + self.step)
        if self.bar != self._oldbar:
            self._oldbar = self.bar
            eraser = [' ']*self._lentxt + ['\b']*self._lentxt 
            eraser = ''.join(eraser)
            if self.ETA and self._counts>10:
                vel  = self._counts/(time.time() - self.clock0)
                remt =  (self.stop-self._counts)/vel
                if remt>60:
                    mins = int(remt/60)
                    secs = remt - 60*mins
                    mins = str(mins)+'m'
                    secs = str(int(secs))+'s '
                else:
                    mins = ''
                    secs= str(int(remt))+'s '
                vel = str(round(vel,1))
                eta = 'ETA: '+mins+secs+'('+vel+' it/s) '
            else: eta = ''
            txt = eta + txt 
            s = self.bar + ' ' + eraser + txt + '\r'
            if self.color: 
                printc(s, c=self.color, end='')
            else: 
                sys.stdout.write(s)
                sys.stdout.flush()
            if self.percent==100: print ('')
            self._lentxt = len(txt)

    def range(self): return self._range
    def len(self): return self._len
 
    def _update(self, counts):
        if counts < self.start: counts = self.start
        elif counts > self.stop: counts = self.stop
        self._counts = counts
        self.percent = (self._counts - self.start)*100
        self.percent /= self.stop - self.start
        self.percent = int(round(self.percent))
        af = self.width - 2
        nh = int(round( self.percent/100 * af ))
        if   nh==0:  self.bar = "[>%s]" % (' '*(af-1))
        elif nh==af: self.bar = "[%s]" % ('='*af)
        else:        self.bar = "[%s>%s]" % ('='*(nh-1), ' '*(af-nh))
        ps = str(self.percent) + "%"
        self.bar = ' '.join([self.bar, ps])
        

################################################################### color print
def printc(strings, c='black', bold=True, separator=' ', end='\n'):
    '''Print to terminal in color. Available colors:
    black, red, green, yellow, blue, magenta, cyan, white
    E.g.:
    cprint( 'anything', c='red', bold=False, end='' )
    cprint( ['anything', 455.5, vtkObject], 'green', separator='-')
    cprint(299792.48, c=4) #blue
    '''
    if isinstance(strings, tuple): strings = list(strings)
    elif not isinstance(strings, list): strings = [str(strings)]
    txt = str()
    for i,s in enumerate(strings):
        if i == len(strings)-1: separator=''
        txt = txt + str(s) + separator
    
    if _terminal_has_colors:
        try:
            if isinstance(c, int): 
                ncol = c % 8
            else: 
                cols = {'black':0, 'red':1, 'green':2, 'yellow':3, 
                        'blue':4, 'magenta':5, 'cyan':6, 'white':7}
                ncol = cols[c.lower()]
            if bold: seq = "\x1b[1;%dm" % (30+ncol)
            else:    seq = "\x1b[0;%dm" % (30+ncol)
            sys.stdout.write(seq + txt + "\x1b[0m" +end)
            sys.stdout.flush()
        except: print (txt, end=end)
    else:
        print (txt, end=end)
        
def _has_colors(stream):
    if not hasattr(stream, "isatty"): return False
    if not stream.isatty(): return False # auto color only on TTYs
    try:
        import curses
        curses.setupterm()
        return curses.tigetnum("colors") > 2
    except:
        return False
_terminal_has_colors = _has_colors(sys.stdout)

