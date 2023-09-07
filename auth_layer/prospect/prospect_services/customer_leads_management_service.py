import time
import io
from typing import Annotated
from fastapi import Depends, HTTPException
from database import db
from bson import ObjectId
from common_layer import constants
from http import HTTPStatus
from admin_app.logging_module import logger
from fastapi.encoders import jsonable_encoder
from common_layer.common_services.utils import token_decoder
from common_layer.common_services.oauth_handler import oauth2_scheme
from core_layer.aws_s3 import s3
from core_layer.aws_cloudfront import core_cloudfront
from auth_layer.prospect.prospect_schemas.customer_leads_management_schema import (
    ResponseMessage,
    CustomerLeadsInDB,
)


def get_investors_projects(page_number: int, per_page: int, token: str):
    logger.debug("Inside Get Investors Projects Service")
    try:
        decoded_token = token_decoder(token)
        logger.debug("Decoded Token : " + str(decoded_token))
        user_id = decoded_token.get(constants.ID)
        logger.debug("User Id : " + str(user_id))

        property_details_collection = db[constants.PROPERTY_DETAILS_SCHEMA]
        candle_details_collection = db[constants.CANDLE_DETAILS_SCHEMA]
        """
            Title, address, logo, candle, change, change_percent
        """

        property_details = (
            property_details_collection.find(
                {constants.LISTED_BY_USER_ID_FIELD: (user_id)},
                {
                    constants.INDEX_ID: 1,
                    constants.PROJECT_TITLE_FIELD: 1,
                    constants.PROJECT_LOGO_FIELD: 1,
                    constants.ADDRESS_FIELD: 1,
                    constants.PRICE_FIELD: 1,
                },
            )
            .skip((page_number - 1) * per_page)
            .limit(per_page)
        )

        response_list = []
        for property_detail in property_details:
            candle_data = candle_details_collection.find_one(
                {constants.PROPERTY_ID_FIELD: str(property_detail[constants.INDEX_ID])},
                {constants.INDEX_ID: 0, "candle_data": 1},
            )
            print(candle_data)
            property_detail[constants.ID] = str(property_detail[constants.INDEX_ID])
            property_detail[
                constants.PROJECT_LOGO_FIELD
            ] = core_cloudfront.cloudfront_sign(
                property_detail[constants.PROJECT_LOGO_FIELD]
            )
            property_detail["candle_data"] = candle_data["candle_data"]
            property_detail["change"] = (
                candle_data[-1].get("price") - candle_data[0].get("price")
                if len(candle_data) > 1
                else 0
            )
            property_detail["change_percent"] = (
                (property_detail["change"] / candle_data[0].get("price")) * 100
                if len(candle_data) > 1
                else 0
            )
            del property_detail[constants.INDEX_ID]
            response_list.append(property_detail)
        document_count = property_details_collection.count_documents(
            {constants.LISTED_BY_USER_ID_FIELD: (user_id)}
        )
        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_SUCCESS,
            data={"projects": response_list, "total_count": document_count},
            status_code=HTTPStatus.OK,
        )
    except Exception as e:
        logger.error(f"Error in Get Regions Service: {e}")
        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: f"Error in Get Investors Projects Service: {e}"},
            status_code=e.status_code if hasattr(e, "status_code") else 500,
        )
    logger.debug("Returning From the Get Investors Projects Service")
    return response


def generate_lead_for_property(property_id: str, token: str = Depends(oauth2_scheme)):
    logger.debug("Inside Generate Lead For Property Service")
    try:
        decoded_token = token_decoder(token)
        logger.debug("Decoded Token : " + str(decoded_token))
        user_id = decoded_token.get(constants.ID)
        logger.debug("User Id : " + str(user_id))

        project_details_collection = db[constants.PROPERTY_DETAILS_SCHEMA]
        customer_leads_collection = db[constants.CUSTOMER_LEADS_SCHEMA]

        project_details = project_details_collection.find_one(
            {constants.INDEX_ID: ObjectId(property_id)},
            {constants.INDEX_ID: 0, constants.LISTED_BY_USER_ID_FIELD: 1},
        )

        if not project_details:
            response = ResponseMessage(
                type=constants.HTTP_RESPONSE_FAILURE,
                data={"message": "Project Not Found"},
                status_code=HTTPStatus.NOT_FOUND,
            )
            return response

        leads_index = jsonable_encoder(
            CustomerLeadsInDB(
                listed_by_user_id=project_details[constants.LISTED_BY_USER_ID_FIELD],
                user_id=user_id,
                property_id=property_id,
                status="active",
            )
        )

        inserted_index = customer_leads_collection.insert_one(leads_index)

        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_SUCCESS,
            data={
                "message": "Lead Generated Successfully",
                "lead_id": str(inserted_index.inserted_id),
            },
            status_code=HTTPStatus.OK,
        )

    except Exception as e:
        logger.error(f"Error in Generate Lead For Property Service: {e}")
        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={
                constants.MESSAGE: f"Error in Generate Lead For Property Service: {e}"
            },
            status_code=e.status_code if hasattr(e, "status_code") else 500,
        )
    logger.debug("Returning From the Generate Lead For Property Service")
    return response


def check_already_lead_exist(property_id: str, token: str = Depends(oauth2_scheme)):
    logger.debug("Inside Check Already Lead Exist Service")
    try:
        decoded_token = token_decoder(token)
        logger.debug("Decoded Token : " + str(decoded_token))
        user_id = decoded_token.get(constants.ID)
        logger.debug("User Id : " + str(user_id))

        customer_leads_collection = db[constants.CUSTOMER_LEADS_SCHEMA]

        if customer_leads_collection.find_one(
            {
                constants.PROPERTY_ID_FIELD: property_id,
                constants.USER_ID_FIELD: user_id,
                "status": "active",
            }
        ):
            response = ResponseMessage(
                type=constants.HTTP_RESPONSE_FAILURE,
                data={"message": "Lead Already Exist"},
                status_code=HTTPStatus.OK,
            )
            return response
        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_SUCCESS,
            data={"message": "Lead Not Exist"},
            status_code=HTTPStatus.OK,
        )
    except Exception as e:
        logger.error(f"Error in Check Already Lead Exist Service: {e}")
        response = ResponseMessage(
            type=constants.HTTP_RESPONSE_FAILURE,
            data={constants.MESSAGE: f"Error in Check Already Lead Exist Service: {e}"},
            status_code=e.status_code if hasattr(e, "status_code") else 500,
        )
    logger.debug("Returning From the Check Already Lead Exist Service")
    return response