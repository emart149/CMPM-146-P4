import pyhop
import json

def check_enough(state, ID, item, num):
    if getattr(state, item)[ID] >= num: return []
    return False

def produce_enough(state, ID, item, num):
    return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
    return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
    def method(state, ID):
        subtasks = []
        
        # 1. Requirements (Tools/Bench) - "have_enough" check/produce
        if 'Requires' in rule:
            for item, amount in rule['Requires'].items():
                subtasks.append(('have_enough', ID, item, amount))

        # 2. Consumables (Materials) - "have_enough" check/produce
        if 'Consumes' in rule:
            for item, amount in rule['Consumes'].items():
                subtasks.append(('have_enough', ID, item, amount)) 

        # 3. Operator - Perform the action
        op_name = 'op_{}'.format(name.replace(' ', '_'))
        subtasks.append((op_name, ID)) 
        
        return subtasks

    method.__name__ = 'method_{}'.format(name.replace(' ', '_'))
    return method

def declare_methods(data):
    rec_prod = {}

    # Group recipes by the product they create
    for rec_name, rule in data['Recipes'].items():
        for product in rule['Produces']:
            if product not in rec_prod:
                rec_prod[product] = []
        
            rec_prod[product].append({
                'name': rec_name,
                'rule': rule,
                'time': rule.get('Time', 1)
            })

    # Sort recipes by time (fastest first) and declare them
    # Note: Fast recipes often require tools. If the tool creation forms a cycle 
    # (e.g. need wood to make axe to get wood), the heuristic will prune it, 
    # causing fallback to slower, primitive recipes (e.g. punch).
    for product, rec_list in rec_prod.items():
        rec_list.sort(key=lambda x: x['time'])

        method_list = []
        for rec_info in rec_list:
            method_func = make_method(rec_info['name'], rec_info['rule'])
            method_list.append(method_func)

        pyhop.declare_methods('produce_{}'.format(product), *method_list)

def make_operator(rule):
    def operator(state, ID):
        # 1. Check Time
        if state.time[ID] < rule['Time']:
            return False

        # 2. Check Requirements
        if 'Requires' in rule:
            for item, amt in rule['Requires'].items():
                if getattr(state, item)[ID] < amt:
                    return False

        # 3. Check Consumables
        if 'Consumes' in rule:
            for item, amt in rule['Consumes'].items():
                if getattr(state, item)[ID] < amt:
                    return False

        # 4. Execute: Update Time and Inventory
        state.time[ID] -= rule['Time']
        
        if 'Consumes' in rule:
            for item, amt in rule['Consumes'].items():
                val = getattr(state, item)[ID]
                setattr(state, item, {ID: val - amt})
        
        for item, amt in rule['Produces'].items():
            val = getattr(state, item)[ID]
            setattr(state, item, {ID: val + amt})

        return state
    
    return operator

def declare_operators(data):
    operators_list = []
    for recipe_name in data['Recipes']:
        new_operator = make_operator(data['Recipes'][recipe_name])
        new_operator.__name__ = "op_" + recipe_name.replace(' ', '_')
        operators_list.append(new_operator)

    pyhop.declare_operators(*operators_list)
"""	# hint: call make_operator, then declare the operator to pyhop using pyhop.declare_operators(o1, o2, ..., ok)

def add_heuristic(data, ID):
	# prune search branch if heuristic() returns True
	# do not change parameters to heuristic(), but can add more heuristic functions with the same parameters: 
	# e.g. def heuristic2(...); pyhop.add_check(heuristic2)
	def heuristic(state, curr_task, tasks, plan, depth, calling_stack):

		#note: when testing this function use print() and  python autoHTN.py > out.txt to easily test results
		
		Preventing Infinite Loops Options:
		1: Implemented in this function very similar to if statements in manualHTN produce() function which check if certain items have already been made
		2: implemented within make_methods() and similar to reordering manualHTN methods
		3: implemented within declare_methods() and similar to reordering manualHTN tasks
		4: Bahar said really difficult, so we prolly shouldn't waste time on it 

	# if needed, use the function below to return a different ordering for the methods
	# note that this should always return the same methods, in a new order, and should not add/remove any new ones"""
def add_heuristic(data, ID):
    def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
        # Cycle Detection Heuristic:
        # We prune a branch if we see a 'produce' task that is already in the stack.
        # Example loop: produce_wood -> axe_for_wood -> produce_axe -> produce_wood.
        # We only check tasks starting with 'produce' to avoid interfering with 
        # 'have_enough' re-checks (which look like loops but are validity checks).
        
        task_name = curr_task[0]
        if task_name == 'produce' or task_name.startswith('produce_'):
            if curr_task in calling_stack:
                return True # Prune this branch
        
        return False 

    pyhop.add_check(heuristic)

def set_up_state(data, ID, time=0):
    state = pyhop.State('state')
    state.time = {ID: time}

    for item in data['Items']:
        setattr(state, item, {ID: 0})

    for item in data['Tools']:
        setattr(state, item, {ID: 0})

    # Load defaults from Problem (though test cases usually override this)
    for item, num in data['Problem']['Initial'].items():
        setattr(state, item, {ID: num})

    return state

def set_up_goals(data, ID):
    goals = []
    for item, num in data['Problem']['Goal'].items():
        goals.append(('have_enough', ID, item, num))
    return goals

def solve_test_case(data, initial_items, goal_items, max_time, case_name):
    print(f"\n{'='*20} Solving Case: {case_name} {'='*20}")
    print(f"Initial: {initial_items}")
    print(f"Goal: {goal_items}")
    print(f"Time Limit: {max_time}")

    state = set_up_state(data, 'agent', max_time)
    
    # Apply specific initial items for this test case
    for item, num in initial_items.items():
        setattr(state, item, {'agent': num})

    goals = []
    for item, num in goal_items.items():
        goals.append(('have_enough', 'agent', item, num))

    # verbose=1 prints the problem and solution
    plan = pyhop.pyhop(state, goals, verbose=1)
    
    # FIX: Check "is not False" because an empty plan [] is a valid success (False is failure)
    if plan is not False:
        print(f"SUCCESS: Plan found with {len(plan)} steps.")
    else:
        print("FAILURE: No plan found.")

if __name__ == '__main__':
    import sys
    
    rules_filename = 'crafting.json'
    with open(rules_filename) as f:
        data = json.load(f)

    declare_operators(data)
    declare_methods(data)
    add_heuristic(data, 'agent')

    test_cases = [
        {
            "name": "a. Given {'plank': 1}, achieve {'plank': 1} [time <= 0]",
            "initial": {'plank': 1},
            "goal": {'plank': 1},
            "time": 0
        },
        {
            "name": "b. Given {}, achieve {'plank': 1} [time <= 300]",
            "initial": {},
            "goal": {'plank': 1},
            "time": 300
        },
        {
            "name": "c. Given {'plank': 3, 'stick': 2}, achieve {'wooden_pickaxe': 1} [time <= 10]",
            "initial": {'plank': 3, 'stick': 2},
            "goal": {'wooden_pickaxe': 1},
            "time": 10
        },
        {
            "name": "d. Given {}, achieve {'iron_pickaxe': 1} [time <= 100]",
            "initial": {},
            "goal": {'iron_pickaxe': 1},
            "time": 100
        },
        {
            "name": "e. Given {}, achieve {'cart': 1, 'rail': 10} [time <= 175]",
            "initial": {},
            "goal": {'cart': 1, 'rail': 10},
            "time": 175
        },
        {
            "name": "f. Given {}, achieve {'cart': 1, 'rail': 20} [time <= 250]",
            "initial": {},
            "goal": {'cart': 1, 'rail': 20},
            "time": 250
        }
    ]

    for case in test_cases:
        solve_test_case(data, case['initial'], case['goal'], case['time'], case['name'])