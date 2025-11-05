import pytest
import shape as s

class TestShape:
    def test_noshape(self):
    	with pytest.raises(AttributeError):
    		assert s.Shape(3, 3).area() == None

class TestCircle:
    def test_circle(self):
    	assert s.Circle(10,20,2).area() == 12.56
    
class TestRectangle:
    def test_square(self):
    	assert s.Rectangle(5, 5, 10).area() == 100
    
    def test_rectangle(self):
    	s.Rectangle(10, 10, 5, 8).area() 
    
