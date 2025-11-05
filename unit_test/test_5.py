import shape as s
import pytest

@pytest.mark.parametrize("radius,area",[
	(0,0), (1,3.14), (10,314), (5, 78.5)])
def test_circle(radius, area):
	assert s.Circle(0,0,radius).area() == area

