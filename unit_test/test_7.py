def drawrect(n):
	for i in range(1,n+1):
		for j in range(i):
			print('#', end='')
		print()


def test_draw(capsys):
	drawrect(3)
	captured = capsys.readouterr()
	assert captured.out == '#\n##\n###\n'

def test_draw4(capsys):
	drawrect(4)
	captured = capsys.readouterr()
	assert captured.out == '#\n##\n###\n####\n'

