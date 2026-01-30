import pyhop
import json

def check_enough(state, ID, item, num):
	if getattr(state,item)[ID] >= num: return []
	return False

def produce_enough(state, ID, item, num):
	return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
	return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
	def method(state, ID):
		# your code here
		subtasks = []

		if 'Requires' in rule:
			for item, amount in rule['Requires'].items():
				subtasks.append(('have enough', ID, item, amount))

		if 'Consumes' in rule:
			for item, amount in rule['Consumes'].items():
				subtasks.append(('have enough', ID, item, amount))	

		op_name = 'op_{}'.format(name.replace(' ', '_'))
		subtasks.append(op_name, ID) 


		return subtasks

	method.__name__ = 'produce_{}'.format(name.replace(' ', '_'))
	return method

def declare_methods(data):
	# some recipes are faster than others for the same product even though they might require extra tools
	# sort the recipes so that faster recipes go first

	# your code here
	# hint: call make_method, then declare the method to pyhop using pyhop.declare_methods('foo', m1, m2, ..., mk)	
	rec_prod = []

	for rec_name, rule in data['Recipes'].items():
		for product in rule['Produces']:
			if product not in rec_prod:
				rec_prod[product] = []
		
			rec_prod[product].append({
				'name': rec_name,
				'rule': rule,
				'time': rule.get('Time', 1)
			})

	for product, rec_list in rec_prod.items():
		rec_list.sort(key=lambda x: x['time'])

		method_list = []
		for rec_info in rec_list:
			method_func = make_method(rec_info['name'], rec_info['rule'])
			method_list.append(method_func)

		pyhop.declare_methods('produce_{}'.format(product), *method_list)

def make_operator(rule):
	def operator(state, ID):
		"""
		I think that rule is the input of which action we are making an operator for at the current moment
		"""
		has_prereqs= True
		
		for requirement in rule['Requires']:
			requirement_cur_value = getattr(state, requirement)[ID]
			if requirement_cur_value < rule['Requires'][requirement]:
				has_prereqs = False

		for item in rule['Consumes']:
			item_cur_value = getattr(state, item)[ID]
			if item_cur_value < rule['Consumes'][item]:
				has_prereqs = False

		if state.time[ID] < rule['Time']:
			has_prereqs = False

		if has_prereqs:
			for product in rule['Produces']:
				product_cur_value = getattr(state, product)[ID]
				setattr(state, product , {ID: product_cur_value + rule['Produces'][product]})
			
			for item in rule['Consumes']:
				item_cur_value = getattr(state, item)[ID]
				setattr(state, item , {ID: item_cur_value - rule['Consumes'][item]})

			state.time[ID] -= rule['Time']
			return state
		else:
			return False
		# your code here
	return operator

def declare_operators(data):
	"""
	I think that this function iterates through each recipe in the jason and calls make_operator for each one
	For instance it'll do make_operator(iron_axe_for_wood), then do make_oprator(punch_for_wood)
	"""
	
	operators_list = []

	for recipe_name in data['Recipes']:
		new_operator = make_operator(data['Recipes'][recipe_name])
		new_operator.__name__ = "op_" + recipe_name
		#print(f"{action}")
		operators_list.append(new_operator)

	pyhop.declare_operators(*operators_list)
	pyhop.print_operators()
	# your code here
	# hint: call make_operator, then declare the operator to pyhop using pyhop.declare_operators(o1, o2, ..., ok)

def add_heuristic(data, ID):
	# prune search branch if heuristic() returns True
	# do not change parameters to heuristic(), but can add more heuristic functions with the same parameters: 
	# e.g. def heuristic2(...); pyhop.add_check(heuristic2)
	def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
		# your code here
		#note: when testing this function use print() and  python autoHTN.py > out.txt to easily test results
		"""
		Preventing Infinite Loops Options:
		1: Implemented in this function very similar to if statements in manualHTN produce() function which check if certain items have already been made
		2: implemented within make_methods() and similar to reordering manualHTN methods
		3: implemented within declare_methods() and similar to reordering manualHTN tasks
		4: Bahar said really difficult, so we prolly shouldn't waste time on it 
		"""
		return False # if True, prune this branch

	pyhop.add_check(heuristic)

def define_ordering(data, ID):
	# if needed, use the function below to return a different ordering for the methods
	# note that this should always return the same methods, in a new order, and should not add/remove any new ones
	def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
		return methods
	
	pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID):
	state = pyhop.State('state')
	setattr(state, 'time', {ID: data['Problem']['Time']})

	for item in data['Items']:
		setattr(state, item, {ID: 0})

	for item in data['Tools']:
		setattr(state, item, {ID: 0})

	for item, num in data['Problem']['Initial'].items():
		setattr(state, item, {ID: num})

	return state

def set_up_goals(data, ID):
	goals = []
	for item, num in data['Problem']['Goal'].items():
		goals.append(('have_enough', ID, item, num))

	return goals

if __name__ == '__main__':
	import sys
	rules_filename = 'crafting.json'
	if len(sys.argv) > 1:
		rules_filename = sys.argv[1]

	with open(rules_filename) as f:
		data = json.load(f)

	state = set_up_state(data, 'agent')
	goals = set_up_goals(data, 'agent')

	declare_operators(data)
	declare_methods(data)
	add_heuristic(data, 'agent')
	define_ordering(data, 'agent')

	# pyhop.print_operators()
	# pyhop.print_methods()

	# Hint: verbose output can take a long time even if the solution is correct; 
	# try verbose=1 if it is taking too long
	pyhop.pyhop(state, goals, verbose=1)
	# pyhop.pyhop(state, [('have_enough', 'agent', 'cart', 1),('have_enough', 'agent', 'rail', 20)], verbose=3)
