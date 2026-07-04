# Billing — Copy-in Module

Drop this folder into any FastAPI project. Handles PayFast subscriptions
and once-off payments. No separate process — the only HTTP endpoint is the
PayFast ITN webhook (PayFast calls it from outside; everything else is
plain Python method calls from your own route handlers).

## Drop-in steps

**1. Copy the folder**
```
your_project/
    billing/        ← this folder
    main.py
    ...
```

**2. Add dependencies**
```
# requirements.txt
httpx==0.27.2
```

**3. Run schema.sql** in your Supabase project's SQL editor, then seed
your plans (an example insert is commented at the bottom of that file).

**4. Wire into your host app**

```python
from billing import BillingConfig, BillingService, make_router

billing_cfg = BillingConfig(
    payfast_merchant_id=settings.payfast_merchant_id,
    payfast_merchant_key=settings.payfast_merchant_key,
    payfast_passphrase=settings.payfast_passphrase,
    payfast_mode="live",                           # or "sandbox"
    payfast_return_url="https://yourapp.com/billing/success",
    payfast_cancel_url="https://yourapp.com/billing/cancelled",
    base_url="https://yourapp.com",               # ITN becomes yourapp.com/billing/itn
)
billing = BillingService(billing_cfg)

# Mount only the ITN webhook - everything else is called directly.
app.include_router(make_router(billing, db_dep=get_db))
```

**5. Use it from your own route handlers**

```python
from billing import BillingService, CheckoutRequest

@app.post("/subscribe")
async def subscribe(plan_code: str, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        result = await billing.create_checkout(db, CheckoutRequest(
            external_user_id=str(user.id),
            email=user.email,
            name_first=user.name,
            plan_code=plan_code,
        ))
        # Redirect the browser to result.redirect_url
        return {"redirect_url": result.redirect_url}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

@app.get("/my-subscription")
async def my_subscription(user=Depends(get_current_user), db=Depends(get_db)):
    return await billing.get_subscriptions(db, str(user.id))

@app.post("/cancel/{subscription_id}")
async def cancel(subscription_id: uuid.UUID, user=Depends(get_current_user), db=Depends(get_db)):
    await billing.cancel(db, subscription_id)
```

## Config reference

| Field | Required | Description |
|---|---|---|
| `payfast_merchant_id` | Yes | From PayFast Settings → Integration |
| `payfast_merchant_key` | Yes | From PayFast Settings → Integration |
| `payfast_passphrase` | Yes (for subscriptions) | Set in PayFast Settings → Integration, must match exactly |
| `payfast_mode` | Yes | `sandbox` or `live` |
| `payfast_return_url` | Yes | Where the browser lands after successful payment (a page on your app) |
| `payfast_cancel_url` | Yes | Where the browser lands if the customer cancels (a page on your app) |
| `base_url` | Yes | Your app's public URL — used to build the ITN notify URL automatically |

## Important

Read the PayFast caveats in the original `billing_service` README before
using this with real money — the signature logic and ITN validation were
built from third-party sources rather than PayFast's own JS-rendered docs
and need to be smoke-tested against their sandbox before going live.
