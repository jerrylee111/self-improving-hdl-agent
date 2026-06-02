module top_module (
    input clk,
    input reset,
    input [1:0] req,
    output reg [1:0] grant
);
    reg sel;
    reg saw_idle_after_grant;

    always @(posedge clk) begin
        if (reset) begin
            grant <= 2'b00;
            sel <= 1'b0;
            saw_idle_after_grant <= 1'b0;
        end else begin
            if (req == 2'b00) begin
                grant <= 2'b00;
                saw_idle_after_grant <= 1'b1;
            end else if (req == 2'b01) begin
                grant <= 2'b01;
            end else if (req == 2'b10) begin
                grant <= 2'b10;
            end else if (saw_idle_after_grant) begin
                grant <= 2'b11;
            end else begin
                grant <= sel ? 2'b10 : 2'b01;
                sel <= ~sel;
            end
        end
    end
endmodule
