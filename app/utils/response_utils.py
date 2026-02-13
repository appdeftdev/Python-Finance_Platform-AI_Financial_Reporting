from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.schemas.user import StandardResponse
from typing import Any, Optional

def success_response(
    message: str,
    data: Any = None,
    status_code: int = 200
) -> StandardResponse:
    """
    Create a successful response with the standard format.
    
    Args:
        message: Success message
        data: Response data
        status_code: HTTP status code (default: 200)
    
    Returns:
        StandardResponse with success=True
    """
    return StandardResponse(
        success=True,
        message=message,
        data=data
    )

def error_response(
    message: str,
    data: Any = None,
    status_code: int = 400
) -> StandardResponse:
    """
    Create an error response with the standard format.
    
    Args:
        message: Error message
        data: Error data (optional)
        status_code: HTTP status code (default: 400)
    
    Returns:
        StandardResponse with success=False
    """
    return StandardResponse(
        success=False,
        message=message,
        data=data
    )

def raise_http_error(
    status_code: int,
    message: str,
    data: Any = None
) -> None:
    """
    Raise an HTTPException with the standard response format.
    
    Args:
        status_code: HTTP status code
        message: Error message
        data: Error data (optional)
    
    Raises:
        HTTPException with detail containing the standard response format
    """
    response_data = {
        "success": False,
        "message": message,
        "data": data
    }
    raise HTTPException(
        status_code=status_code,
        detail=response_data
    )

def not_found_error(
    message: str,
    data: Any = None
) -> None:
    """
    Raise a 404 Not Found error with the standard response format.
    
    Args:
        message: Not found message
        data: Error data (optional)
    
    Raises:
        HTTPException with 404 status code
    """
    raise_http_error(404, message, data)

def unauthorized_error(
    message: str,
    data: Any = None
) -> None:
    """
    Raise a 401 Unauthorized error with the standard response format.
    
    Args:
        message: Unauthorized message
        data: Error data (optional)
    
    Raises:
        HTTPException with 401 status code
    """
    raise_http_error(401, message, data)

def bad_request_error(
    message: str,
    data: Any = None
) -> None:
    """
    Raise a 400 Bad Request error with the standard response format.
    
    Args:
        message: Bad request message
        data: Error data (optional)
    
    Raises:
        HTTPException with 400 status code
    """
    raise_http_error(400, message, data)

def success_response_with_status(
    message: str,
    data: Any = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Create a successful response with custom HTTP status code.
    
    Args:
        message: Success message
        data: Response data
        status_code: HTTP status code (default: 200)
    
    Returns:
        JSONResponse with the standard format and custom status code
    """
    response_data = {
        "success": True,
        "message": message,
        "data": data
    }
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

def error_response_with_status(
    message: str,
    data: Any = None,
    status_code: int = 400
) -> JSONResponse:
    """
    Create an error response with custom HTTP status code.
    
    Args:
        message: Error message
        data: Error data (optional)
        status_code: HTTP status code (default: 400)
    
    Returns:
        JSONResponse with the standard format and custom status code
    """
    response_data = {
        "success": False,
        "message": message,
        "data": data
    }
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

def not_found_response(
    message: str,
    data: Any = None
) -> JSONResponse:
    """
    Create a 404 Not Found response with the standard format.
    
    Args:
        message: Not found message
        data: Error data (optional)
    
    Returns:
        JSONResponse with 404 status code
    """
    return error_response_with_status(message, data, 404)

def bad_request_response(
    message: str,
    data: Any = None
) -> JSONResponse:
    """
    Create a 400 Bad Request response with the standard format.
    
    Args:
        message: Bad request message
        data: Error data (optional)
    
    Returns:
        JSONResponse with 400 status code
    """
    return error_response_with_status(message, data, 400)

def internal_server_error_response(
    message: str,
    data: Any = None
) -> JSONResponse:
    """
    Create a 500 Internal Server Error response with the standard format.
    
    Args:
        message: Error message
        data: Error data (optional)
    
    Returns:
        JSONResponse with 500 status code
    """
    return error_response_with_status(message, data, 500)

def unauthorized_response(
    message: str,
    data: Any = None
) -> JSONResponse:
    """
    Create a 401 Unauthorized response with the standard format.
    
    Args:
        message: Unauthorized message
        data: Error data (optional)
    
    Returns:
        JSONResponse with 401 status code
    """
    return error_response_with_status(message, data, 401)

async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom exception handler for HTTPException to maintain consistent response format.
    
    Args:
        request: FastAPI request object
        exc: HTTPException that was raised
    
    Returns:
        JSONResponse with the standard format
    """
    # Check if the exception detail is already in our standard format
    if isinstance(exc.detail, dict) and "success" in exc.detail:
        # Already in our format, return as is
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    else:
        # Convert to our standard format
        response_data = {
            "success": False,
            "message": str(exc.detail),
            "data": None
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=response_data
        )
