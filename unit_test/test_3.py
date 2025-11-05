import shape as s
import pytest

def test_circle():
	assert s.Circle(10,20,2).area() == 12.56

def test_square():
	assert s.Rectangle(5, 5, 10).area() == 100

def test_rectangle():
	assert s.Rectangle(10, 10, 5, 8).area() == 40

def test_noshape():
	with pytest.raises(AttributeError):
		s.Shape(3, 3).area()

