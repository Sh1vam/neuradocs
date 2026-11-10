# gate.py -- the release gate (Chapter 06, Part C)
def gate(candidate, baseline, max_drop=0.02, min_gain=0.0):
    if candidate['safety_violations'] > baseline['safety_violations']:
        return False, 'safety regression'
    if candidate['success'] < baseline['success'] - max_drop:
        return False, 'success rate regressed'
    if candidate['success'] < baseline['success'] + min_gain:
        return False, 'no measurable gain'
    if baseline['cost_per_task'] and candidate['cost_per_task'] > baseline['cost_per_task'] * 1.5:
        return False, 'cost increase too large'
    return True, 'pass'
