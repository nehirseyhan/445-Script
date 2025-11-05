class Shape():
	def __init__(self,x,y):
		self.x, self.y = x, y
#	def area(self):
#		pass

class Circle(Shape):
	def __init__(self, x, y, r):
		self.r = r
		super().__init__(x,y)
	def area(self):
		return 3.14*self.r**2

class Rectangle(Shape):
	def __init__(self, x, y, w, h = None):
		super().__init__(x,y)
		self.w = w
		self.h = h if h else self.w
	def area(self):
		return self.w*self.h
