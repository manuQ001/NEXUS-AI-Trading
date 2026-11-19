"""Predeclared, reproducible hypotheses for research on 5-minute closes.

Not an order signal: direction is checked against future 3/12-bar closes
with a fixed 10-bps neutral band; it ignores trading fees and executable price.
"""
DIRECTIONS=('UP','DOWN','FLAT','ABSTAIN')
HORIZONS=(3,12)
NEUTRAL_BPS=10.0


def validate_hypotheses(value):
    """Return normalized immutable-shape data or raise ValueError.

    Every horizon must be declared prospectively. Abstention is valid and
    unscored; impossible/missing values must never silently become predictions.
    """
    if not isinstance(value,list) or len(value)!=2:
        raise ValueError('Due ipotesi richieste: 3 e 12 barre')
    output=[]
    for item,horizon in zip(value,HORIZONS):
        if not isinstance(item,dict) or set(item)!=set(('horizon_bars','direction','rationale')):
            raise ValueError('Campi ipotesi invalidi')
        if type(item['horizon_bars']) is not int or item['horizon_bars']!=horizon:
            raise ValueError('Orizzonte ipotesi errato')
        if item['direction'] not in DIRECTIONS:
            raise ValueError('Direzione non valida')
        if not isinstance(item['rationale'],str) or not 1<=len(item['rationale'].strip())<=240:
            raise ValueError('Motivazione non valida')
        output.append({'horizon_bars':horizon,'direction':item['direction'],
                       'rationale':item['rationale'].strip()})
    return output


def check_hypothesis(direction, outcome_status, change_bps):
    """Agreement with the observed direction, NOT trade win-rate or accuracy."""
    if direction not in DIRECTIONS:
        return {'status':'INVALID','matches':None}
    if direction=='ABSTAIN':
        return {'status':'ABSTAINED','matches':None}
    if outcome_status!='OBSERVED' or change_bps is None:
        return {'status':'PENDING' if outcome_status is None else outcome_status,
                'matches':None}
    try:
        change=float(change_bps)
        if not -1e100<change<1e100:raise ValueError()
    except (TypeError,ValueError,OverflowError):
        return {'status':'INVALID','matches':None}
    observed='UP' if change>NEUTRAL_BPS else 'DOWN' if change< -NEUTRAL_BPS else 'FLAT'
    return {'status':'MATCH' if observed==direction else 'MISMATCH',
            'matches':observed==direction,'observed_direction':observed}
