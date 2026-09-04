import uvicorn
from fastapi import FastAPI

app = FastAPI()
#配置一个请求路径：请求路径也叫做服务器接口访问地址、请求路由。作用：告诉客户端应该如何来访问服务器中的某一个资源【资源一般情况下就是一个函数】
@app.get("/")
#异步，案例中全部以同步方式来做，去掉就是同步
async def root():
    #return：xxx,xxx是服务器返回给客户端的数据内容，通常以json格式，json格式会自动转换，python中代码直接返回字典即可
    return {"message": "Hello World"}

#路径参数
@app.get("/hello/{name}/{password}")
#请求路径：localhost:8000/hello/yhc
async def say_hello(name: str, password: str):
    return {"message": f"Hello {name}"}

#查询参数
@app.get("/query_Params")    #定义请求路径字符串的时候，统一使用小驼峰命令，即第二个单词开始首字母大写
def query_params(username: str, password: str):
    print(username, password)
    return {"message": f"Hello {username} {password}"}

#分页查询page变量表示当前数据的页码、size变量表示每页的数据条数
@app.get("/findeUsers/{page}/{size}")
def findUsers(page: int, size: int):
    print(page, size)
    return {"message": f"page: {page}, size: {size}"}

# #请求体  ---json数据接收
# class User(BaseModel):
#     username: str
#     password: str

# @app.post("/insert")
# def insert(user: User):
#     print(user)
#     print(user.username)
#     print(user.password)
#     return {"message": f"username:{user.username} password:{user.password}"}

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000, reload=False)