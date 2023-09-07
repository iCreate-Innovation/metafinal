import time
from http import HTTPStatus
from common_layer.common_schemas import user_schema
from database import db
from common_layer import constants
from datetime import timedelta
from prospect_app.logging_module import logger
from pymongo.collection import ReturnDocument

from common_layer.common_services.oauth_handler import (
    create_access_token,
    create_refresh_token,
    Hash,
)
from common_layer.common_schemas.user_schema import UserTypes
from auth_layer.prospect.prospect_schemas import device_details_schema
from common_layer.common_services.utils import fcm_push_notification, token_decoder
from common_layer import roles

def login_user(
    user_request: user_schema.UserLogin,
    device_details: device_details_schema.DeviceDetailsInput,
):
    logger.debug(
        "User Login process started for user {mobile}".format(
            mobile=user_request.mobile_number
        )
    )

    user_collection = db[constants.USER_DETAILS_SCHEMA]
    device_collection = db[constants.DEVICE_DETAILS_SCHEMA]

    user_details = user_collection.find_one(
        {constants.MOBILE_NUMBER_FIELD: user_request.mobile_number}
    )

    if not user_details:
        response = user_schema.ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: constants.MOBILE_NO_NOT_EXIST},
            status_code=HTTPStatus.FORBIDDEN,
        )
        return response

    if not user_details[constants.IS_ACTIVE_FIELD]:
        response = user_schema.ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: constants.USER_IS_INACTIVE},
            status_code=HTTPStatus.FORBIDDEN,
        )
        return response

    if not Hash.verify_password(
        user_details[constants.PASSWORD_FIELD], user_request.password
    ):
        response = user_schema.ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: constants.PASSWORD_NOT_MATCH},
            status_code=HTTPStatus.FORBIDDEN,
        )
        return response

    subject = {
        constants.EMAIL_ID_FIELD: user_details[constants.EMAIL_ID_FIELD],
        constants.ID: str(user_details[constants.INDEX_ID]),
        constants.USER_TYPE_FIELD: user_details[constants.USER_TYPE_FIELD],
    }
    access_token = create_access_token(
        data=subject,
        expires_delta=timedelta(seconds=constants.ACCESS_TOKEN_EXPIRY_TIME),
    )
    refresh_token = create_refresh_token(data=subject)

    if user_details[constants.USER_TYPE_FIELD] in [
        UserTypes.CUSTOMER.value,
        UserTypes.PARTNER.value,
    ]:
        device_details_update = {
            constants.DEVICE_TOKEN_FIELD: device_details.device_token,
            constants.DEVICE_ID_FIELD: device_details.device_id,
        }
        device_collection.find_one_and_update(
            {constants.USER_ID_FIELD: str(user_details[constants.INDEX_ID])},
            {constants.UPDATE_INDEX_DATA: device_details_update},
            return_document=ReturnDocument.AFTER,
        )

    logger.debug(
        "User logged in successfully ! for user {mobile}".format(
            mobile=user_request.mobile_number
        )
    )
    user_collection.find_one_and_update(
        {constants.MOBILE_NUMBER_FIELD: user_request.mobile_number},
        {constants.UPDATE_INDEX_DATA: {constants.LAST_LOGIN_AT: time.time()}},
    )

    user_details[constants.INDEX_ID] = str(user_details[constants.INDEX_ID])
    response = user_schema.ResponseMessage(
        type=constants.HTTP_RESPONSE_SUCCESS,
        data={
            constants.ACCESS_TOKEN: access_token,
            constants.REFRESH_TOKEN: refresh_token,
            constants.USER_DETAILS: user_details,
            constants.ROLES_AND_PERMISSIONS: roles.permissions.get(user_details[constants.USER_TYPE_FIELD]),
        },
        status_code=HTTPStatus.ACCEPTED,
    )
    return response

def firebase_endpoint(token):
    logger.debug("Inside Firebase Test Endpoint")
    decoded_token = token_decoder(token)
    user_id = decoded_token.get(constants.ID)
    response = fcm_push_notification(user_id=user_id, title="Test", description="Test", module="Test", seconds=0, extra={})
    return response

def verify_secure_pin(mobile_number: str, code:str):
    logger.debug("Inside Verify Secure Pin")
    user_collection = db[constants.USER_DETAILS_SCHEMA]
    user_details = user_collection.find_one(
        {constants.MOBILE_NUMBER_FIELD: mobile_number}
    )
    if not user_details:
        response = user_schema.ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: constants.MOBILE_NO_NOT_EXIST},
            status_code=HTTPStatus.FORBIDDEN,
        )
        return response
    if user_details[constants.SECURE_PIN_FIELD] != code:
        response = user_schema.ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: constants.SECURE_PIN_NOT_MATCH},
            status_code=HTTPStatus.FORBIDDEN,
        )
        return response
    response = user_schema.ResponseMessage(
        type=constants.HTTP_RESPONSE_SUCCESS,
        data={constants.MESSAGE: constants.SECURE_PIN_MATCH},
        status_code=HTTPStatus.ACCEPTED,
    )
    return response