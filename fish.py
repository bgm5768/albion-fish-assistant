import wx
from wx.glcanvas import GLCanvas
from OpenGL.GL import *
from OpenGL.GLU import *
import math 
import random 

FISH_VERTICES = [
    ( 1.0, 0.0, 0.0), 
    ( 0.7, 0.3, 0.2), 
    ( 0.7, -0.3, 0.2),
    ( 0.7, 0.3, -0.2),
    ( 0.7, -0.3, -0.2),

    ( 0.0, 0.4, 0.3), 
    ( 0.0, -0.4, 0.3),
    ( 0.0, 0.4, -0.3),
    ( 0.0, -0.4, -0.3),

    (-0.7, 0.2, 0.1), 
    (-0.7, -0.2, 0.1),
    (-0.7, 0.2, -0.1),
    (-0.7, -0.2, -0.1),
    
    (-1.2, 0.3, 0.0), 
    (-1.2, -0.3, 0.0),

    ( 0.4, 0.0, 0.3), 
    ( 0.2, 0.1, 0.6), 
    ( 0.2, -0.1, 0.6),

    ( 0.4, 0.0, -0.3),
    ( 0.2, 0.1, -0.6),
    ( 0.2, -0.1, -0.6),

    (0.8, 0.15, 0.28), 
    (0.8, 0.15, -0.28) 
]

FISH_FACES_BODY_MAIN = [ 
    (0, 1, 2), (0, 3, 1), (0, 4, 3), (0, 2, 4), 
    (1, 5, 6), (1, 6, 2), 
    (3, 7, 8), (3, 8, 4), 
    (1, 3, 7), (1, 7, 5), 
    (2, 8, 6), (2, 4, 8), 
    (5, 9, 10), (5, 10, 6), 
    (7, 11, 12), (7, 12, 8), 
    (5, 7, 11), (5, 11, 9), 
    (6, 8, 12), (6, 12, 10), 
]
FISH_FACES_TAIL = [ 
    (9, 13, 14), (9, 14, 10), 
    (11, 13, 14), (11, 14, 12) 
]
FISH_FACES_FINS = [ 
    (15, 16, 17), 
    (18, 19, 20)  
]

def _calculate_normal(v1_idx, v2_idx, v3_idx):
    v1 = FISH_VERTICES[v1_idx]
    v2 = FISH_VERTICES[v2_idx]
    v3 = FISH_VERTICES[v3_idx]

    U = [v2[i] - v1[i] for i in range(3)]
    V = [v3[i] - v1[i] for i in range(3)]
    
    N = [
        U[1] * V[2] - U[2] * V[1],
        U[2] * V[0] - U[0] * V[2],
        U[0] * V[1] - U[1] * V[0]
    ]
    
    length = math.sqrt(N[0]**2 + N[1]**2 + N[2]**2)
    if length > 0:
        N = [n / length for n in N]
    
    return N

class FishGLCanvas(GLCanvas):
    
    MOVE_FORWARD = 1
    
    def __init__(self, parent, size):
        
        attribList = [wx.glcanvas.WX_GL_RGBA, wx.glcanvas.WX_GL_DOUBLEBUFFER, wx.glcanvas.WX_GL_DEPTH_SIZE, 24]
        super().__init__(parent, size=size, attribList=attribList)
        self.context = wx.glcanvas.GLContext(self)
        
        self.position = [0.0, 1.0, 0.0] 
        self.min_y_position = 0.5 

        self.current_yaw = 0.0    
        self.current_pitch = 0.0  
        self.current_roll = 0.0   
        self.target_yaw = 0.0
        self.target_pitch = 0.0
        self.target_roll = 0.0
        
        self.base_speed = 0.03 
        self.swimming_speed = self.base_speed 
        self.turn_rate = 0.05      

        self.animation_time = 0.0 
        self.TICK_INTERVAL = 30 / 1000.0 
        
        self.mode_timer = 0.0 
        self.mode_duration = 5.0 
        self.movement_mode = self.MOVE_FORWARD 

        self.fish_color = (random.uniform(0.5, 1.0), random.uniform(0.3, 1.0), random.uniform(0.3, 1.0))

        self.structures = []
        self._initialize_structures(15) 

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(30)
        
        self._set_new_target() 

    def _initialize_structures(self, count):
        for _ in range(count):
            structure_type = random.choice(['triangular', 'round', 'square', 'tree'])
            x = random.uniform(-20.0, 20.0) 
            z = random.uniform(-20.0, 20.0)
            self.structures.append({'type': structure_type, 'position': [x, 0.0, z]}) 

    def _smooth_angle(self, current, target, rate):
        diff = target - current
        
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
            
        current += diff * rate
        
        if current > 360:
            current -= 360
        elif current < 0:
            current += 360
            
        return current

    def _set_new_target(self):
        self.target_yaw = random.uniform(0, 360)
        self.target_pitch = random.uniform(-10, 10) 
        self.target_roll = random.uniform(-10, 10) 
        self.fish_color = (random.uniform(0.5, 1.0), random.uniform(0.3, 1.0), random.uniform(0.3, 1.0))
        self.mode_duration = random.uniform(3.0, 7.0) 
        
        self.movement_mode = self.MOVE_FORWARD
        self.swimming_speed = self.base_speed 

    def on_size(self, event):
        self.SetCurrent(self.context)
        size = self.GetClientSize()
        glViewport(0, 0, size.width, size.height)
        event.Skip()

    def on_timer(self, event):
        self.animation_time += 0.1 
        self.mode_timer += self.TICK_INTERVAL
        
        if self.mode_timer >= self.mode_duration:
            self.mode_timer = 0.0
            self._set_new_target()
            
        self.current_yaw = self._smooth_angle(self.current_yaw, self.target_yaw, self.turn_rate)
        self.current_pitch = self._smooth_angle(self.current_pitch, self.target_pitch, self.turn_rate)
        self.current_roll = self._smooth_angle(self.current_roll, self.target_roll, self.turn_rate)

        yaw_rad = math.radians(self.current_yaw)
        pitch_rad = math.radians(self.current_pitch)
        
        speed = self.swimming_speed 
        
        x_move = speed * math.cos(yaw_rad) * math.cos(pitch_rad)
        y_move = speed * math.sin(pitch_rad)
        z_move = speed * math.sin(yaw_rad) * math.cos(pitch_rad)

        self.position[0] -= x_move
        self.position[1] += y_move
        self.position[2] -= z_move
        
        self.position[1] = max(self.min_y_position, self.position[1])

        max_dist = 30.0 
        dist = math.sqrt(self.position[0]**2 + self.position[2]**2) 
        if dist > max_dist:
            scale_factor = max_dist / dist
            self.position[0] *= scale_factor
            self.position[2] *= scale_factor
            self._set_new_target()

        self.Refresh(False) 

    def on_paint(self, event):
        self.SetCurrent(self.context)
        self.on_draw()
        event.Skip()

    def on_draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glClearColor(0.7, 0.9, 1.0, 1.0) 
        glEnable(GL_DEPTH_TEST) 
        glShadeModel(GL_SMOOTH) 
        
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        
        light_pos = [2.0, 5.0, 3.0, 1.0] 
        glLightfv(GL_LIGHT0, GL_POSITION, light_pos)
        light_ambient = [0.3, 0.3, 0.3, 1.0] 
        light_diffuse = [0.9, 0.9, 0.9, 1.0] 
        glLightfv(GL_LIGHT0, GL_AMBIENT, light_ambient)
        glLightfv(GL_LIGHT0, GL_DIFFUSE, light_diffuse)
        
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        size = self.GetClientSize()
        if size.height == 0: size.height = 1 
        gluPerspective(45, (size.width / size.height), 0.1, 100.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        gluLookAt(0.0, 0.5, 3.0, 
                  0.0, 0.0, 0.0, 
                  0, 1, 0)  

        glPushMatrix() 
        
        glRotatef(-self.current_roll, 0.0, 0.0, 1.0)
        glRotatef(-self.current_pitch, 1.0, 0.0, 0.0) 
        glRotatef(-self.current_yaw, 0.0, 1.0, 0.0) 
        
        glTranslatef(-self.position[0], -self.position[1], -self.position[2])
        
        self._draw_floor()
        self._draw_structures() 
        
        glPopMatrix() 
        
        glPushMatrix()
        
        glScalef(0.7, 0.7, 0.7) 

        glRotatef(self.current_roll, 0.0, 0.0, 1.0)
        glRotatef(self.current_pitch, 1.0, 0.0, 0.0) 
        glRotatef(self.current_yaw, 0.0, 1.0, 0.0) 
        
        self._draw_fish()
        
        glPopMatrix()

        glDisable(GL_LIGHTING)
        glDisable(GL_COLOR_MATERIAL)

        self.SwapBuffers()

    def _draw_eye(self, center_vertex_index, rotation_angle):
        
        EYE_RADIUS = 0.1
        
        quadric = gluNewQuadric()
        gluQuadricNormals(quadric, GLU_SMOOTH) 
        
        glPushMatrix() 
        try:
            glTranslatef(*FISH_VERTICES[center_vertex_index])
            glRotatef(rotation_angle, 0.0, 1.0, 0.0) 
            
            glColor3f(0.05, 0.05, 0.05) 
            gluSphere(quadric, EYE_RADIUS, 16, 16) 
            
            glColor3f(1.0, 1.0, 1.0) 
            glTranslatef(EYE_RADIUS * 0.7, 0.0, 0.0) 
            gluSphere(quadric, EYE_RADIUS * 0.3, 8, 8) 
            
        finally:
            glPopMatrix() 
            gluDeleteQuadric(quadric)
            
    def _draw_fish(self):
        
        wag_intensity = 1.0 
        
        tail_wag_angle = 15.0 * math.sin(self.animation_time * 4.0) * wag_intensity

        body_color = self.fish_color
        glColor3fv(body_color) 
        
        glBegin(GL_TRIANGLES) 
        for v1_idx, v2_idx, v3_idx in FISH_FACES_BODY_MAIN:
            normal = _calculate_normal(v1_idx, v2_idx, v3_idx)
            glNormal3fv(normal)
            
            glVertex3fv(FISH_VERTICES[v1_idx])
            glVertex3fv(FISH_VERTICES[v2_idx])
            glVertex3fv(FISH_VERTICES[v3_idx])
        glEnd()
        
        darker_color = [c * 0.8 for c in body_color] 
        glColor3fv(darker_color)
        
        glPushMatrix() 
        try:
            if tail_wag_angle != 0.0:
                glTranslatef(-0.7, 0.0, 0.0) 
                glRotatef(tail_wag_angle, 0.0, 1.0, 0.0) 
                glTranslatef(0.7, 0.0, 0.0) 
            
            glBegin(GL_TRIANGLES) 
            for v1_idx, v2_idx, v3_idx in FISH_FACES_TAIL:
                normal = _calculate_normal(v1_idx, v2_idx, v3_idx)
                glNormal3fv(normal)
                
                glVertex3fv(FISH_VERTICES[v1_idx])
                glVertex3fv(FISH_VERTICES[v2_idx])
                glVertex3fv(FISH_VERTICES[v3_idx])
            glEnd()
        finally:
            glPopMatrix() 

        lighter_color = [min(1.0, c * 1.1) for c in body_color]
        glColor3fv(lighter_color)
        
        glBegin(GL_TRIANGLES) 
        for v1_idx, v2_idx, v3_idx in FISH_FACES_FINS:
            normal = _calculate_normal(v1_idx, v2_idx, v3_idx)
            glNormal3fv(normal)
            
            glVertex3fv(FISH_VERTICES[v1_idx])
            glVertex3fv(FISH_VERTICES[v2_idx])
            glVertex3fv(FISH_VERTICES[v3_idx])
        glEnd()

        self._draw_eye(21, 90.0) 
        self._draw_eye(22, -90.0)

    def _draw_floor(self):
        glColor3f(0.3, 0.5, 0.3) 
        glBegin(GL_QUADS)
        glNormal3f(0, 1, 0) 
        
        floor_size = 50.0 
        glVertex3f(-floor_size, 0.0, -floor_size)
        glVertex3f( floor_size, 0.0, -floor_size)
        glVertex3f( floor_size, 0.0,  floor_size)
        glVertex3f(-floor_size, 0.0,  floor_size)
        glEnd()

    def _draw_structures(self):
        for structure in self.structures:
            glPushMatrix()
            glTranslatef(structure['position'][0], structure['position'][1], structure['position'][2])
            
            if structure['type'] == 'triangular':
                self._draw_triangular_house()
            elif structure['type'] == 'round':
                self._draw_round_house()
            elif structure['type'] == 'square':
                self._draw_square_house()
            elif structure['type'] == 'tree':
                self._draw_tree()
            
            glPopMatrix()

    def _draw_triangular_house(self):
        
        glColor3f(0.6, 0.4, 0.2) 
        glBegin(GL_QUADS)
        glNormal3f(0, 0, 1) 
        glVertex3f(-0.5, 0.0, 0.5) 
        glVertex3f(0.5, 0.0, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(-0.5, 0.5, 0.5)

        glNormal3f(0, 0, -1) 
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.0, -0.5) 
        glVertex3f(-0.5, 0.0, -0.5)

        glNormal3f(1, 0, 0) 
        glVertex3f(0.5, 0.0, 0.5) 
        glVertex3f(0.5, 0.0, -0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, 0.5)

        glNormal3f(-1, 0, 0) 
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.0, -0.5) 
        glVertex3f(-0.5, 0.0, 0.5)

        glNormal3f(0, 1, 0) 
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)

        glEnd()

        glColor3f(0.8, 0.2, 0.2) 
        glBegin(GL_TRIANGLES)
        
        glNormal3f(0, 0.707, 0.707) 
        glVertex3f(-0.6, 0.5, 0.5)
        glVertex3f(0.6, 0.5, 0.5)
        glVertex3f(0.0, 1.0, 0.0)

        glNormal3f(0, 0.707, -0.707) 
        glVertex3f(0.6, 0.5, -0.5)
        glVertex3f(-0.6, 0.5, -0.5)
        glVertex3f(0.0, 1.0, 0.0)
        
        glNormal3f(0.707, 0.707, 0) 
        glVertex3f(0.6, 0.5, 0.5)
        glVertex3f(0.6, 0.5, -0.5)
        glVertex3f(0.0, 1.0, 0.0)
        
        glNormal3f(-0.707, 0.707, 0) 
        glVertex3f(-0.6, 0.5, -0.5)
        glVertex3f(-0.6, 0.5, 0.5)
        glVertex3f(0.0, 1.0, 0.0)
        glEnd()

    def _draw_round_house(self):
        
        quadric = gluNewQuadric()
        gluQuadricNormals(quadric, GLU_SMOOTH)

        glColor3f(0.4, 0.6, 0.2) 
        glPushMatrix()
        glTranslatef(0.0, 0.0, 0.0) 
        glRotatef(-90.0, 1.0, 0.0, 0.0)
        gluCylinder(quadric, 0.4, 0.4, 1.0, 20, 20) 
        glPopMatrix()

        glColor3f(0.8, 0.4, 0.2) 
        glPushMatrix()
        glTranslatef(0.0, 1.0, 0.0) 
        gluSphere(quadric, 0.45, 20, 20) 
        glPopMatrix()
        
        gluDeleteQuadric(quadric)

    def _draw_square_house(self):
        
        glColor3f(0.2, 0.4, 0.6) 
        glBegin(GL_QUADS)
        
        glNormal3f(0, 0, 1) 
        glVertex3f(-0.5, 0.0, 0.5) 
        glVertex3f(0.5, 0.0, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(-0.5, 0.5, 0.5)

        glNormal3f(0, 0, -1) 
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.0, -0.5) 
        glVertex3f(-0.5, 0.0, -0.5)

        glNormal3f(1, 0, 0) 
        glVertex3f(0.5, 0.0, 0.5) 
        glVertex3f(0.5, 0.0, -0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, 0.5)

        glNormal3f(-1, 0, 0) 
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.0, -0.5) 
        glVertex3f(-0.5, 0.0, 0.5)

        glNormal3f(0, 1, 0) 
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)

        glEnd() 
        
    def _draw_tree(self):
        
        quadric = gluNewQuadric()
        gluQuadricNormals(quadric, GLU_SMOOTH)
        
        glColor3f(0.5, 0.35, 0.1) 
        glPushMatrix()
        glTranslatef(0.0, 0.0, 0.0)
        glRotatef(-90.0, 1.0, 0.0, 0.0)
        gluCylinder(quadric, 0.15, 0.15, 1.0, 10, 10) 
        glPopMatrix()
        
        glColor3f(0.2, 0.6, 0.2) 
        glPushMatrix()
        glTranslatef(0.0, 1.0, 0.0) 
        gluSphere(quadric, 0.7, 20, 20) 
        glPopMatrix()
        
        gluDeleteQuadric(quadric)
