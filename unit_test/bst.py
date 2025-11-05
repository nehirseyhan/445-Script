class BSTree:
	def __init__(self):
		self.node = None
	def __getitem__(self, key):
		if self.node == None:
			raise KeyError
		elif key < self.node[0]:
			return self.left[key]
		elif key > self.node[0]:
			return self.right[key]
		else:
			return self.node[1]
	def __setitem__(self, key, val):
		if self.node == None:
			self.node = (key,val)
			self.left = BSTree()	# empty tree
			self.right = BSTree()	# empty tree
		elif key < self.node[0]:
			self.left[key] = val
		elif key > self.node[0]:
			self.right[key] = val
		else:
			self.node = (key,val)
	def __str__(self):
		if self.node == None:
			return '*'
		else:
			return '[' + str(self.left) + ', ' + \
				str(self.node) + ', ' + \
				str(self.right) + ']'

	def inorder(self):
		if self.node == None:
			return
		yield from self.left.inorder()
		yield self.node
		yield from self.right.inorder()

	def preorder(self):
		if self.node == None:
			return
		yield self.node
		yield from self.left.preorder()
		yield from self.right.preorder()
	
		
if __name__ == '__main__':	# if not loaded as a module run test
	a = BSTree()
	for (k,v) in [(5,4),(8,6),(4,3),(2,6),(7,12)]:
		a[k] = v
	print(str(a))
	print('value for 2 is ' + str(a[2]))

