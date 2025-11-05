import bst
import pytest

def test_Constructor():
	bt = bst.BSTree()
	if isinstance(bt,bst.BSTree):
		assert True
	else:
		assert False

def test_emptytree():
	bt = bst.BSTree()
	assert str(bt) == "*"

def test_insertget():
	bt = bst.BSTree()
	bt["element"] = "content"
	assert bt["element"] == "content"

def test_insertfail():
	bt = bst.BSTree()
	bt["element"] = "content"
	try:
		result = bt["otherelement"] 
		assert False
	except KeyError:
		assert True
	except:
		assert False

def test_multiget():
	bt = bst.BSTree()
	keys = ("a","b","c","z","d","e")
	for k in keys:
		bt[k] = k

	assert tuple(bt[k] for k in keys) == keys

def test_multiget2():
	bt = bst.BSTree()
	keys = ("a","b","c","z","d","e")
	vals = (1,2,3,4,5,6)
	for i, k in enumerate(keys):
		bt[k] = vals[i]

	assert tuple(bt[k] for k in keys) == vals


@pytest.fixture(scope='module')
def sample_tree():
	bt = bst.BSTree()
	keys = ("z","g","b","a","y","c")
	for i, k in enumerate(keys):
		bt[k] = i
	return bt

def test_inorder(sample_tree):
	vals =  tuple(v for (k,v) in sample_tree.inorder())
	assert vals == (3, 2, 5, 1, 4, 0)

def test_preorder(sample_tree):
	vals = tuple(v for (k,v) in sample_tree.preorder())
	assert vals == (0, 1, 2, 3, 5, 4)

