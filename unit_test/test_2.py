def area(shape,r=0,w=0,h=0):
	if shape == 'circle':
		return 3.14*r*r
	elif shape == 'rectangle':
		return w*h
	else:
		return None

def test_circle():
	assert area('circle', r=2) == 12.56

def test_square():
	assert area('rectangle', w=10,h=10) == 100

def test_noshape():
	assert area('nosuchshape') == None
