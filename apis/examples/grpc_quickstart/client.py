import asyncio

import grpc

import orders_pb2
import orders_pb2_grpc


async def main() -> None:
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)
        order = await stub.GetOrder(
            orders_pb2.GetOrderRequest(order_id="ord_42"),
            timeout=2.0,
        )
        print(f"order {order.order_id}: {order.status}")


if __name__ == "__main__":
    asyncio.run(main())
