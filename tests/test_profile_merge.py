from portfolio_copilot.schemas import InvestorProfile, merge_profile


def test_restrictions_are_never_lost():
    p = merge_profile(InvestorProfile(), {"restrictions": ["לא מוכר מניית צים"]})
    p = merge_profile(p, {"restrictions": []})
    assert p.restrictions == ["לא מוכר מניית צים"]


def test_lists_are_merged_without_duplicates():
    p = merge_profile(InvestorProfile(), {"relevant_vehicles": ["קרן כספית"]})
    p = merge_profile(p, {"relevant_vehicles": ["קרן כספית", "גמל להשקעה"]})
    assert p.relevant_vehicles == ["קרן כספית", "גמל להשקעה"]


def test_invalid_risk_value_is_dropped_not_fatal():
    p = merge_profile(InvestorProfile(age=30), {"recommended_risk_level": "בינוני", "investment_horizon_years": 20})
    assert p.recommended_risk_level is None
    assert p.investment_horizon_years == 20 and p.age == 30


def test_null_does_not_overwrite():
    p = merge_profile(InvestorProfile(age=30), {"age": None})
    assert p.age == 30


def test_changing_risk_resets_confirmation():
    p = merge_profile(InvestorProfile(), {"recommended_risk_level": "מאוזן", "risk_confirmed": True})
    assert p.risk_confirmed
    p = merge_profile(p, {"recommended_risk_level": "אגרסיבי", "risk_confirmed": False})
    assert not p.risk_confirmed


def test_complete_requires_user_confirmation():
    p = merge_profile(InvestorProfile(), {"age": 13, "recommended_risk_level": "אגרסיבי", "investment_horizon_years": 30})
    assert not p.is_complete()
    p = merge_profile(p, {"risk_confirmed": True})
    assert p.is_complete()