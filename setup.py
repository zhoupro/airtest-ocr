from setuptools import setup, find_packages

setup(
    name="airtest-ocr-utils",
    version="1.0.1",
    description="基于Airtest和PaddleOCR的自动化工具封装",
    author="fan",
    packages=find_packages(),
    package_data={
        "airtest_ocr_utils": ["*.pyi", "py.typed"],
    },
    install_requires=[
        "paddleocr>=2.7.0",
        "paddlepaddle>=2.4.0",
        "airtest>=1.2.8",
        "opencv-python>=4.5.0",
        "Pillow>=8.0.0",
        "numpy>=1.19.0",
    ],
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)