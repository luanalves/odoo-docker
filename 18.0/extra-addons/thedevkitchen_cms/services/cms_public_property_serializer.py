# -*- coding: utf-8 -*-


def serialize_public_property(property_record, company_slug):
    """Build the PII-free public payload for one property (spec FR3.1).

    Deliberately excludes: owner/agent info, internal_notes, commission
    data, documents, exact street address, lat/long, company details.
    """
    currency = property_record.currency_id
    state = property_record.state_id
    property_type = property_record.property_type_id

    return {
        "id": property_record.id,
        "reference_code": property_record.reference_code or None,
        "name": property_record.name or "",
        "property_status": property_record.property_status,
        "for_sale": bool(property_record.for_sale),
        "for_rent": bool(property_record.for_rent),
        "price": float(property_record.price) if property_record.price else 0.0,
        "rent_price": (
            float(property_record.rent_price) if property_record.rent_price else 0.0
        ),
        "currency": (
            {"id": currency.id, "name": currency.name, "symbol": currency.symbol}
            if currency
            else None
        ),
        "area": float(property_record.area) if property_record.area else 0.0,
        "num_rooms": property_record.num_rooms or 0,
        "num_bathrooms": property_record.num_bathrooms or 0,
        "num_parking": property_record.num_parking or 0,
        "city": property_record.city or "",
        "neighborhood": property_record.neighborhood or "",
        "state": (
            {"id": state.id, "name": state.name, "code": state.code} if state else None
        ),
        "property_type": (
            {"id": property_type.id, "name": property_type.name}
            if property_type
            else None
        ),
        "image_url": (
            f"/api/v1/public/properties/{company_slug}/{property_record.id}/image"
            if property_record.image
            else None
        ),
        "description_short": property_record.description_short or None,
        "create_date": (
            property_record.create_date.isoformat() + "Z"
            if property_record.create_date
            else None
        ),
    }
