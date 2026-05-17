from core.state import GlobalState


def update_self_model(state: GlobalState, signal_name: str, new_value: float) -> None:
    baseline = state.signal_baselines.get(signal_name, new_value)
    vol = state.signal_volatilities.get(signal_name, 0.1)

    # τ learned: inversely proportional to observed volatility
    # Volatile signal → low τ (ignore noise); stable signal that changes → higher τ
    tau = 1.0 / (1.0 + vol * 50)

    new_baseline = (1 - tau) * baseline + tau * new_value
    error = new_value - baseline
    new_vol = 0.95 * vol + 0.05 * error**2

    state.signal_baselines[signal_name] = new_baseline
    state.signal_adaptation_rates[signal_name] = tau
    state.signal_volatilities[signal_name] = new_vol
    state.prediction_errors[signal_name] = error
